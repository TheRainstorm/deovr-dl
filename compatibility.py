import json
import re
import time

def get_video_data(response):
    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', response.text)
    if not match:
        return None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    return video_data
        
def get_video_json_from_videoData(video_data):
    # convert encodings
    encodings = []
    encoding_index = {}
    for src in video_data['src']:
        encoding = src['encoding']
        if encoding not in encoding_index:
            encoding_index[encoding] = {
                "name": encoding,
                "videoSources": []
            }
        encoding_index[encoding]['videoSources'].append({
            "resolution": src['height'],
            'height': src['height'],
            'width': src['width'],
            "url": src['url']
        })
    
    for encoding in encoding_index:
        encodings.append(encoding_index[encoding])
    
    if len(encodings) == 0:
        # video data have not enough info(for example premium video), convert will failed
        return None
    
    screenType = "flat"
    # "flat" - flat 2d video
    # "dome" - 180 degrees equirect mesh
    # "sphere" - 360 degrees equirect mesh
    # "fisheye" - 180 degrees fisheye mesh
    # "mkx200" - 200 degrees fisheye mesh
    # "rf52" - 190 degrees Canon fisheye mesh
    if video_data['angle'] == 180:
        screenType = "dome"
    elif video_data['angle'] == 360:
        screenType = "sphere"
    
    video_json = {
        "encodings": encodings,
        "title": video_data['title'],
        "id": video_data['id'],
        "videoLength": video_data['duration'],
        # "is3d":true,
        # "stereoMode" can be set to "sbs" for side by side stereoscopic layout, "tb" for top-bottom layout, "cuv" for custom UV layout (currently only used for Canon RF52 lens) or "off" for monoscopic videos
        "stereoMode": video_data["format"],
        "screenType": screenType,
        "skipIntro":0,
        
        # Video preview, will be used to show the rewind of the file in the player.
        "videoThumbnail": video_data['rewindVideo'],
        #  Neccessary thumbnail and preview (optional) in case of playing from Selection Scene
        "thumbnailUrl": video_data['posterURL'],  # The field ‘thumbnailUrl’ should contain the link to the file with the image shown in the list.
        "videoPreview": video_data['rewindVideo'], # The field ‘videoPreview’ contains the link to the video file, which is shown when moving the cursor to this video in the list.
        "timelinePreview": "",
        
        # useful
        "description": video_data['title'],
        "date": int(time.time()),  # use current time
        
        # others
        "isFavorite": video_data['isFavorite'],
        "viewAngle": video_data['angle'],
        # "projection": "unset", # video_data is 0
        "quantity": {
            "comments": 0,
            "favorites": video_data['likes'],
            "views": 0,
        },
    }
    
    return video_json
