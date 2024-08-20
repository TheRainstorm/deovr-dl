import argparse
import json
import re
import os
import subprocess
import ffmpeg
import urllib.parse
from PIL import Image

from donwloader import seconds_to_hms

def ffmpeg_probe(file_path):
    probe = ffmpeg.probe(file_path)
    
    duration = float(probe["format"]["duration"])
    
    video_stream = probe['streams'][0]
    
    encoding = video_stream['codec_name']
    if encoding in ['h264', 'avc']:
        encoding = 'h264'
    elif encoding in ['h265', 'hevc']:
        encoding = 'h265'
    
    meta_data = {
        "duration": duration,
        "encoding": encoding,
        "width": video_stream['width'],
        "height": video_stream['height'],
        "resolution": video_stream['height'],
    }
    return meta_data

def make_thumbnail(video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data):
    thumbnail_file = os.path.join(thumbnail_dir, f"{title}_thumbnail.jpg")
    videoPreview_file = os.path.join(preview_dir, f"{title}_preview.mp4")
    videoThumbnail_file = os.path.join(seeklookup_dir, f"{title}_seek.mp4")
    timelinePreview_file = os.path.join(seeklookup_dir, f"{title}_4096_timelinePreview341x195.jpg")  # 4096_timelinePreview341x195
    
    thumbnailUrl = f"{args.server}/{urllib.parse.quote(os.path.relpath(thumbnail_file, root_dir))}"
    videoPreview = f"{args.server}/{urllib.parse.quote(os.path.relpath(videoPreview_file, root_dir))}"
    videoThumbnail = f"{args.server}/{urllib.parse.quote(os.path.relpath(videoThumbnail_file, root_dir))}"
    timelinePreview = f"{args.server}/{urllib.parse.quote(os.path.relpath(timelinePreview_file, root_dir))}"
    
    def get_scale_str(video_width, video_height, crop_width, crop_height):
        scale_str = f"scale=-1:{crop_height},crop={crop_width}:{crop_height}"
        if video_width / video_height < crop_width / crop_height:
            scale_str = f"scale={crop_width}:-1,crop={crop_width}:{crop_height}"
        return scale_str

    width = meta_data['width']
    height = meta_data['height']
    crop_half_str = ""
    if args.stereoMode == 'sbs':
        crop_half_str = 'crop=iw/2:ih:0:0,'
        width //= 2
    elif args.stereoMode == 'tb':
        crop_half_str = 'crop=iw:ih/2:0:0,'
        height //= 2
        
    overwrite_str = '-y' if args.force_thumbnail & 1 else '-n'
    
    '''thumbnail'''
    if not os.path.exists(thumbnail_file) \
        or args.force_thumbnail & 1:
        print("generating thumbnail")
        scale_str = get_scale_str(width, height, 420, 252)
        
        if args.thumbnail_start_time >= 0:
            start = seconds_to_hms(args.thumbnail_start_time)
        else:
            start = seconds_to_hms(meta_data['duration']//2)
        cmd = f"ffmpeg -ss {start} -i '{video_path}' -vframes 1 -q:v 2 -vf '{crop_half_str}{scale_str}' '{thumbnail_file}' {overwrite_str}"
        # print(cmd)
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
        
    '''video preview'''
    if not os.path.exists(videoPreview_file) \
        or args.force_thumbnail & 2:
        # 15s, crop to 330x200
        print("generating preview video")
        scale_str = get_scale_str(width, height, 330, 200)
        overwrite_str = '-y' if args.force_thumbnail & 2 else '-n'
        last = min(meta_data['duration'], 15)
        
        subprocess.run(f"ffmpeg -i '{video_path}' -t {last} -an -vf '{crop_half_str}{scale_str}' -c:v libx264 -crf 23 -preset ultrafast '{videoPreview_file}' {overwrite_str}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    '''seeking preivew video'''
    if not os.path.exists(videoThumbnail_file):
        videoThumbnail = ""
    # !!! obsolescent
    # print("generating seek preview video")
    # overwrite_str = '-y' if args.force_thumbnail & 4 else '-n'
    # fps = 5
    # subprocess.run(f"ffmpeg -i '{video_path}' -an -vf 'fps={fps},{crop_half_str}{scale_str}' -c:v libx264 -crf 23 -preset ultrafast '{videoThumbnail_file}' {overwrite_str}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    '''timeline preview'''
    if not os.path.exists(timelinePreview_file) \
        or args.force_thumbnail & 8:
        # shortcut num_frames picture and composite one 4096x4096 picture
        print("generating timeline preview image")
        crop_width, crop_height = 341, 195
        collage_width = collage_height = 4096
        grid_size = [collage_width//crop_width, collage_height//crop_height]
        num_frames = grid_size[0]*grid_size[1]  # 252
        
        frame_interval = meta_data['duration'] / num_frames
        scale_str = get_scale_str(width, height, crop_width, crop_height)
        
        image_temp_dir = os.path.join(seeklookup_dir, f"{title}_timelinePreview")
        os.makedirs(image_temp_dir, exist_ok=True)
        cmd = f"ffmpeg -i '{video_path}' -an -vf 'fps=1/{frame_interval},{crop_half_str}{scale_str}' '{image_temp_dir}'/%04d.png"
        # print(cmd)
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # composite
        collage = Image.new('RGB', (collage_width, collage_height))
        for i in range(num_frames):
            try:
                img = Image.open(f"{image_temp_dir}/{i+1:04d}.png")
                x = (i % grid_size[0]) * crop_width
                y = (i // grid_size[0]) * crop_height
                collage.paste(img, (x, y))
            except Exception as e:
                print(f"Error: {e}")
                break
        collage.save(timelinePreview_file)
        # clean
        os.system(f"rm -rf '{image_temp_dir}'")

    return thumbnailUrl, videoPreview, videoThumbnail, timelinePreview

def create_video_json(playlist, title, video_path, meta_data, screenType="flat", stereoMode="sbs"):
    global current_video_id
    
    ext = os.path.splitext(video_path)[1]
    video_url = f"{args.server}/{urllib.parse.quote(f'{playlist}/metadata/json/{title}.json')}"
    video_src_url = f"{args.server}/{urllib.parse.quote(os.path.relpath(video_path, root_dir))}"
    
    duration_sec = int(meta_data['duration'])
    video_json = {
        "encodings":[
        {
            "name": meta_data['encoding'],
            "videoSources":[
            {
                "resolution": meta_data['resolution'],
                'height': meta_data['height'],
                'width': meta_data['width'],
                "url": video_src_url
            }
            ]
        }
        ],
        "title": title,
        "id": current_video_id,
        "videoLength": duration_sec,
        "is3d": True,
        "screenType": screenType,
        "stereoMode": stereoMode,
        "skipIntro": 0,
        'video_url': video_url,
        "ext": ext,
        
        # Video preview, will be used to show the rewind of the file in the player.
        "videoThumbnail": "",
        #  Neccessary thumbnail and preview (optional) in case of playing from Selection Scene
        "thumbnailUrl": "",  # The field ‘thumbnailUrl’ should contain the link to the file with the image shown in the list.
        "videoPreview": "", # The field ‘videoPreview’ contains the link to the video file, which is shown when moving the cursor to this video in the list.
        "timelinePreview": "",
    }
    
    return video_json

def check_encoding(encodings, encoding, resolution):
    if len(encodings)==0:
        return 3 # not exist same title video
    encoding_index = {}
    for e in encodings:
        encoding_index[e['name']] = e
    
    if encoding not in encoding_index:
        # new encoding
        return 2 # new encoding
    else:
        for s in encoding_index[encoding]['videoSources']:
            if s['resolution'] == resolution:
                return 0 # already exists
        return 1 # same encoding, new resolution
    
def add_encoding(encodings, encoding, videoSource):
    if len(encodings) == 0:
        encodings.append({
            'name': encoding,
            'videoSources': [videoSource]
        })
        return 3 # not exist same title video
    
    encoding_index = {}
    for e in encodings:
        encoding_index[e['name']] = e
    
    if encoding not in encoding_index:
        # new encoding
        encodings.append({
            'name': encoding,
            'videoSources': [videoSource]
        })
        return 2 # new encoding
    else:
        for s in encoding_index[encoding]['videoSources']:
            if s['resolution'] == videoSource['resolution']:
                return 0 # already exists
        e['videoSources'].append(videoSource)
        return 1 # same encoding, new resolution

def read_top_json(root_dir):
    # read playlist json
    top_json_path = os.path.join(root_dir, 'top.json')
    top_json = {'scenes': [], 'current_id': 0}
    if os.path.exists(top_json_path):
        with open(top_json_path, 'r') as f:
            top_json_tmp = json.load(f)
        if top_json_tmp:  # bad top json file, reset
            top_json = top_json_tmp
    return top_json
    
def get_current_id(top_json):
    return top_json['current_id']

def write_top_json(root_dir, top_json):
    top_json_path = os.path.join(root_dir, 'top.json')
    with open(top_json_path, 'w') as f:
        json.dump(top_json, f, indent=4, ensure_ascii=False)

def add_to_top_json(root_dir, playlist, playlist_video_jsons):
    playlist_video_jsons_short = []
    for single_json in playlist_video_jsons:
        short_single_json = {
            'title': single_json['title'],
            'vidoeLength': single_json['videoLength'],
            'video_url': single_json['video_url'],
            'thumbnail_url': single_json['thumbnailUrl'],
        }
        playlist_video_jsons_short.append(short_single_json)
    
    top_json = read_top_json(root_dir)
    
    scene_index = {}
    for scene in top_json['scenes']:
        scene_index[scene['name']] = scene
    if playlist not in scene_index:
        top_json['scenes'].append({
            'name': playlist,
            'list': playlist_video_jsons_short
        })
        
        top_json['current_id'] += len(playlist_video_jsons_short)
        write_top_json(root_dir, top_json)
        return

    title_index = {}
    for video_json in scene_index[playlist]['list']:
        title_index[video_json['title']] = video_json
    
    playlist_video_jsons_filterd = []
    for video_json in playlist_video_jsons_short:
        if video_json['title'] in title_index:
            continue
        
        playlist_video_jsons_filterd.append(video_json)
    
    # add to top json
    scene_index[playlist]['list'] += playlist_video_jsons_filterd
    
    top_json['current_id'] += len(playlist_video_jsons_filterd)
    write_top_json(root_dir, top_json)

def del_top_json(root_dir, playlist, title):
    top_json = read_top_json(root_dir)
    for scene in top_json['scenes']:
        if scene['name'] != playlist:
            continue
        idx = -1
        for i, video_json in enumerate(scene['list']):
            if video_json['title'] == title:
                idx = i
                break
        if idx==-1:
            print("Warnning: {tilte} not in top json, delete failed")
        else:
            del scene['list'][i]
    write_top_json(root_dir, top_json)
    
def make_dirs(*dirs, exist_ok=False):
    for d in dirs:
        os.makedirs(d, exist_ok=exist_ok)

def remove_files(*files):
    for f in files:
        if os.path.exists(f):
            os.remove(f)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download url from deovr')
    parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
    parser.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')

    parser.add_argument('-P', '--playlist', help='update specific playlist, or scan all playlists')
    parser.add_argument('-V', '--video-file', help='Scan one video')

    parser.add_argument('--screenType', default="flat", help='flat, dome(180), sphere(360)')
    parser.add_argument('--stereoMode', default="sbs", help='sbs, tb')

    parser.add_argument('-s', '--thumbnail-start-time', type=int, default=-1, help='specific thumbnail shot time. default shot at 1/3 duration')
    parser.add_argument('-F', '--force-thumbnail', type=int, default=0, help='bitmask, force regenerate video seek|video preview|thumbnail')

    parser.add_argument('-C', '--clear-not-exist', action="store_true", help='Scan directory, clear not exist video encoding in json')

    args = parser.parse_args()

    root_dir = args.root_dir

    for playlist in os.listdir(root_dir):
        # skip files
        playlist_dir = os.path.join(root_dir, playlist)
        if not os.path.isdir(playlist_dir): 
            continue
        if args.playlist:
            if playlist != args.playlist:
                continue
        print(f"Processing {playlist}")
        
        # re read current id
        top_json = read_top_json(root_dir)
        current_video_id = get_current_id(top_json)

        # prepare dir
        thumbnail_dir = os.path.join(playlist_dir, 'metadata', 'thumbnail')
        preview_dir = os.path.join(playlist_dir, 'metadata', 'preview')
        seeklookup_dir = os.path.join(playlist_dir, 'metadata', 'seeklookup')
        json_dir = os.path.join(playlist_dir, 'metadata', 'json')
        make_dirs(thumbnail_dir, preview_dir, seeklookup_dir, json_dir, exist_ok=True)
        
        if args.clear_not_exist:
            for file in os.listdir(json_dir):
                json_file = os.path.join(json_dir, file)
                with open(json_file, 'r') as f:
                    video_json = json.load(f)
                title = video_json['title']
                print(f"Checking: {title:<50s} ", end='')
                
                del_flag = False # recording change
                encodings = []
                for encoding in video_json['encodings']:
                    videoSources = []
                    for src in encoding['videoSources']:
                        video_path = os.path.join(playlist_dir, f"{title} - {encoding['name']} {src['resolution']}p{video_json['ext']}")
                        if os.path.exists(video_path):
                            videoSources.append(src)
                            # print(f"{encoding['name']} {src['resolution']}p exist")
                        else:
                            print(f"{encoding['name']} {src['resolution']}p not exist")
                            del_flag = True
                    if videoSources:
                        encodings.append({
                            "name": encoding['name'],
                            "videoSources": videoSources
                        })
                if not encodings:
                    # delete title
                    print("delete title metadata")
                    thumbnail_file = os.path.join(thumbnail_dir, f"{title}_thumbnail.jpg")
                    videoPreview_file = os.path.join(preview_dir, f"{title}_preview.mp4")
                    videoThumbnail_file = os.path.join(seeklookup_dir, f"{title}_seek.mp4")
                    remove_files(json_file, thumbnail_file, videoPreview_file, videoThumbnail_file)
                    
                    print("delete title in top json")
                    del_top_json(root_dir, playlist, title)
                elif del_flag:
                    video_json['encodings'] = encodings
                    with open(json_file, 'w') as f:
                        json.dump(video_json, f, indent=4, ensure_ascii=False)
                else:
                    print("exist")
            continue
        
        # scan playlist_dir
        playlist_video_jsons = []
        if args.video_file:
            video_files = [args.video_file]
        else:
            video_files = list(os.listdir(playlist_dir))
        
        for i, video_file in enumerate(video_files):
            # skip not video files
            video_name, ext = os.path.splitext(video_file)
            if ext not in ['.mp4', '.mkv']:
                continue
            
            # get title
            need_fix_filename = False
            m = re.search(r'(?P<title>.*?)\ -\ (?P<encoding>\w+)\ (?P<quality>\w+)\.(?P<ext>\w+)', video_file)
            if m:
                title = m.group('title')  # different encoding is seen as same title
                req_encoding = m.group('encoding')
                quality = m.group('quality')
                req_resolution = int(quality[:-1]) # 1080p -> 1080
            else:
                title = video_name
                need_fix_filename = True  # after fixing, it's easy to add new encoding, rather than adding as new title
            print(f"Processing {i+1:3d}/{len(video_files):<3d}\t {title}")
            
            def probe_and_create(video_path):
                # probe video: encoding, duration, resolution
                meta_data = ffmpeg_probe(video_path)
                
                if need_fix_filename:
                    video_path_fixed = os.path.join(playlist_dir, f"{title} - {meta_data['encoding']} {meta_data['resolution']}p{ext}")
                    os.rename(video_path, video_path_fixed)
                    video_path = video_path_fixed
                
                video_json = create_video_json(playlist, title, video_path, meta_data, screenType=args.screenType, stereoMode=args.stereoMode)
                
                return video_path, meta_data, video_json
            
            video_path = os.path.join(playlist_dir, video_file)
            
            json_file = os.path.join(root_dir, playlist, 'metadata/json', f"{title}.json")
            if not os.path.exists(json_file):
                print(f"Create New video json: {title}")
                
                video_path, meta_data, video_json = probe_and_create(video_path)
            
                # make thumbnail etc.
                thumbnailUrl, videoPreview, videoThumbnail, timelinePreview = make_thumbnail(video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data)
                video_json.update({
                    "videoThumbnail": videoThumbnail,
                    "thumbnailUrl": thumbnailUrl,
                    "videoPreview": videoPreview,
                    "timelinePreview": timelinePreview,
                })
                
                with open(json_file, 'w') as f:
                    json.dump(video_json, f, indent=4, ensure_ascii=False)
                current_video_id += 1
                playlist_video_jsons.append(video_json)
                
                add_to_top_json(root_dir, playlist, [video_json])
            else:
                # read existing json
                with open(json_file, 'r') as f:
                    video_json_ori = json.load(f)
                
                # if 'ext' not in video_json_ori:
                #     print('update ext')
                #     video_json_ori['ext'] = ext
                #     with open(json_file, 'w') as f:
                #         json.dump(video_json_ori, f, indent=4, ensure_ascii=False)
                #     playlist_video_jsons.append(video_json_ori)
                
                # update thumbnail
                if args.force_thumbnail:
                    meta_data = ffmpeg_probe(video_path)
                    thumbnailUrl, videoPreview, videoThumbnail, timelinePreview = make_thumbnail(video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data)
                    video_json_ori.update({
                        "videoThumbnail": videoThumbnail,
                        "thumbnailUrl": thumbnailUrl,
                        "videoPreview": videoPreview,
                        "timelinePreview": timelinePreview,
                    })
                    with open(json_file, 'w') as f:
                        json.dump(video_json_ori, f, indent=4, ensure_ascii=False)
                
                if not need_fix_filename:
                    exist_flag = check_encoding(video_json_ori['encodings'], req_encoding, req_resolution)
                    if exist_flag==0:
                        print(f"Encoding and res Already exists, skip")
                        playlist_video_jsons.append(video_json_ori)
                        continue
                
                print(f"Add new format: {req_encoding} {req_resolution}p")
                # new encoding
                video_path, meta_data, video_json = probe_and_create(video_path)

                # only update encodings, keep original metadata
                add_encoding(video_json_ori['encodings'], video_json['encodings'][0]['name'], video_json['encodings'][0]['videoSources'][0])

                with open(json_file, 'w') as f:
                    json.dump(video_json_ori, f, indent=4, ensure_ascii=False)
                playlist_video_jsons.append(video_json_ori)

        add_to_top_json(root_dir, playlist, playlist_video_jsons)