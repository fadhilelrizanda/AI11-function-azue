import azure.functions as func
from openai import OpenAI
import json
import logging
import requests
import time
import os
from dotenv import load_dotenv
app = func.FunctionApp()

API_OPENAI = os.getenv('OpenAI_client')
openAI_key = os.getenv('OpenAI_KEY')
OpenAI_client = OpenAI(base_url=API_OPENAI, api_key=openAI_key)
subscription_key = os.getenv('subscription_key')
account_id = os.getenv('account_id')
location = os.getenv('location')


def get_access_token():
    url = f"https://api.videoindexer.ai/Auth/{location}/Accounts/{account_id}/AccessToken?allowEdit=true"
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        access_token = response.json()
        return access_token
    else:
        return None


def get_indexed_data(vid_id, access_token):
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    url = f"https://api.videoindexer.ai/{location}/Accounts/{account_id}/Videos/{vid_id}/Index?accessToken={access_token}&language=id-ID"
    response = requests.get(url=url, headers=headers)
    if response.status_code == 200:
        video_data = response.json()
        transcript = video_data.get("videos")[0]["insights"]["transcript"]
        transcript_texts = [texts['text'] for texts in transcript]
        return json.dumps({"transcript": transcript_texts}, ensure_ascii=False)
    else:
        return None


def send_video_to_indexer(access_token, video_url, vid_name):
    headers = {
        "Ocp-Apim-Subscription-Key": subscription_key,
    }
    video_indexer_url = (
        f"https://api.videoindexer.ai/{location}/Accounts/{account_id}"
        f"/Videos?name={vid_name}&privacy=Private&videoUrl={video_url}"
        f"&indexingPreset=AudioOnly&accessToken={access_token}&sendSuccessEmail=False&streamingPreset=NoStreaming&language=id-ID&excludedAI=Faces,ObservedPeople,Emotions,Labels"
    )
    response = requests.post(url=video_indexer_url, headers=headers)
    if response.status_code == 200:
        video_indexer_id = response.json().get("id")
        return video_indexer_id
    else:
        return None


def check_indexing_status(vid_id, access_token):
    headers = {"Ocp-Apim-Subscription-Key": subscription_key}
    url = f"https://api.videoindexer.ai/{location}/Accounts/{account_id}/Videos/{vid_id}/Index?accessToken={access_token}&language=id-ID"
    start_time = time.time()
    max_wait_time = 1800  # 30 minutes timeout
    while True:
        if time.time() - start_time > max_wait_time:
            return False

        response = requests.get(url=url, headers=headers)
        if response.status_code == 200:
            status = response.json().get("state")
            if status == "Processed":
                return True
        time.sleep(60)  # Poll every 60 seconds

    return False


@app.route(route="Get-Summary", auth_level=func.AuthLevel.ANONYMOUS)
def get_summary(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    try:
        text_input = req.get_body().decode('utf-8')
        prompt = req.params.get('prompt')
    except Exception as e:
        logging.error(f"Error reading input string: {e}")
        return func.HttpResponse(
            "Error reading input string.",
            status_code=400
        )

    if text_input and prompt:
        # Process the input string here (for example, log it or modify it)
        message_format = [{"role": "user", "content": f"{prompt}:\n{text_input}"}]
        response = OpenAI_client.chat.completions.create(model='gpt-3.5-turbo',messages= message_format,temperature=1.0,stream=False)
        summerized_text = response.choices[0].message.content
        return func.HttpResponse(summerized_text, status_code=200)
    else:
        return func.HttpResponse(
            "Please pass an input_string in the request body.",
            status_code=400
        )


@app.route(route="get-transcript", auth_level=func.AuthLevel.ANONYMOUS)
def getTranscript(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    video_url = req.params.get('video_url')
    video_name = req.params.get('video_name')
    
    if not video_url or not video_name:
        return func.HttpResponse(
            "Please provide both 'video_url' and 'video_name' in the query string.",
            status_code=400
        )

    access_token = get_access_token()

    if access_token:
        vid_id = send_video_to_indexer(access_token, video_url, video_name)

        if vid_id:
            if check_indexing_status(vid_id, access_token):
                get_text = get_indexed_data(vid_id, access_token)
                return func.HttpResponse(get_text)
            else:
                return func.HttpResponse("Indexing not completed in a reasonable time.", status_code=500)
        else:
            return func.HttpResponse("Failed to index video", status_code=500)
    else:
        return func.HttpResponse("Failed to get access token", status_code=500)

@app.route(route="send-video", auth_level=func.AuthLevel.ANONYMOUS)
def sendVideo(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    video_url = req.params.get('video_url')
    video_name = req.params.get('video_name')
    
    if not video_url or not video_name:
        return func.HttpResponse(
            "Please provide both 'video_url' and 'video_name' in the query string.",
            status_code=400
        )

    access_token = get_access_token()

    if access_token:
        vid_id = send_video_to_indexer(access_token, video_url, video_name)

        if vid_id:
            return func.HttpResponse(vid_id)
        else:
            return func.HttpResponse("Failed to index video", status_code=500)
    else:
        return func.HttpResponse("Failed to get access token", status_code=500)

@app.route(route="fetch-transcript", auth_level=func.AuthLevel.ANONYMOUS)
def fetchTranscript(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    video_id = req.params.get('video_id')
    access_token = get_access_token()

    if not video_id:
         return func.HttpResponse("input video id", status_code=500)
    if access_token:
        get_text = get_indexed_data(video_id, access_token)
        if get_text:
                return func.HttpResponse(get_text)
        
        else:
            return func.HttpResponse("Video not found/processing", status_code=500)

    else:
        return func.HttpResponse("Failed to get access token", status_code=500)


if __name__ == "__main__":
    func.FunctionApp().run()