import glob
import json
import os
import re
import shutil
import subprocess
import ffmpeg
import urllib.parse
from PIL import Image
from donwloader import seconds_to_hms

'''API functions
'''
# db
def read_db_json(root_dir):
    # read playlist json
    db_json_path = os.path.join(root_dir, 'top.json')
    db_json = {'scenes': [], 'current_id': 1000}
    if os.path.exists(db_json_path):
        with open(db_json_path, 'r') as f:
            db_json_tmp = json.load(f)
        if db_json_tmp:  # bad top json file, reset
            db_json = db_json_tmp
    return db_json
    
def get_current_id(db_json):
    return db_json['current_id']

def current_id_inc(db_json):
    db_json['current_id'] += 1

def write_db_json(root_dir, db_json):
    db_json_path = os.path.join(root_dir, 'top.json')
    with open(db_json_path, 'w') as f:
        json.dump(db_json, f, indent=4, ensure_ascii=False)

def get_scene_index(db_json):
    scene_index = {}
    for scene in db_json['scenes']:
        scene_index[scene['name']] = scene
    return scene_index

def get_title_index(scene):
    title_index = {}
    for video_json in scene['list']:
        title_index[video_json['title']] = video_json
    return title_index

# video
def read_video_json(root_dir, playlist, title):
    json_path = os.path.join(root_dir, playlist, "metadata", "json", f"{title}.json")
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    return {}

def write_video_json(root_dir, playlist, title, video_json):
    json_path = os.path.join(root_dir, playlist, "metadata", "json", f"{title}.json")
    with open(json_path, 'w') as f:
        json.dump(video_json, f, indent=4, ensure_ascii=False)

def get_video_formats(video_json):
    formats = []
    for encoding in video_json['encodings']:
        for src in encoding['videoSources']:
            formats.append([encoding['name'], src['width'], src['height']])
    return formats

def delete_title(root_dir, playlist, title):
    db_json = read_db_json(root_dir)
    succ = db_del_title(db_json, playlist, title)
    if succ:
        delete_title_files(root_dir, playlist, title)
        write_db_json(root_dir, db_json)
        return {"status": True, "msg": "success"}
    else:
        return {"status": False, "msg": "Not exist"}
    
def move_title_from_to(root_dir, src_playlist, dst_playlist, title):
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    if src_playlist not in scene_index or dst_playlist not in scene_index:
        print(f"Playlist {src_playlist} or {dst_playlist} not found")
        return {"status": False, "msg": f"Playlist {src_playlist} or {dst_playlist} not found"}
    
    # update json
    json_path = os.path.join(root_dir, src_playlist, "metadata", "json", f"{title}.json")
    json_text_new = replace_file_playlist(json_path, src_playlist, dst_playlist)
    video_json = json.loads(json_text_new)
    
    # move files
    move_title_files(root_dir, src_playlist, dst_playlist, title)
    
    # update db
    db_json = read_db_json(root_dir)
    db_del_title(db_json, src_playlist, title)
    db_add_title(db_json, dst_playlist, video_json)
    write_db_json(root_dir, db_json)
    return {"status": True, "msg": "success"}

def rename_playlist(root_dir, src_playlist, dst_playlist):
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    if dst_playlist in scene_index:
        print(f"Playlist {dst_playlist} already exists")
        return {"status": False, "msg": f"Playlist {dst_playlist} already exists"}
    
    # rename playlist dir
    os.rename(os.path.join(root_dir, src_playlist), os.path.join(root_dir, dst_playlist))
    
    # update json files
    json_dir = os.path.join(root_dir, dst_playlist, "metadata", "json")
    for file in os.listdir(json_dir):
        if file.endswith(".json"):
            json_path = os.path.join(json_dir, file)
            replace_file_playlist(json_path, src_playlist, dst_playlist)
    
    # update db
    scene_index[src_playlist]['name'] = dst_playlist
    write_db_json(root_dir, db_json)
    return {"status": True, "msg": "success"}

def change_server(root_dir, old_server, new_server):
    playlist_info = {}
    for playlist in os.listdir(root_dir):
        playlist_path = os.path.join(root_dir, playlist)
        if not os.path.isdir(playlist_path):
            continue
        if 'metadata' in os.listdir(playlist_path):
            playlist_info[playlist] = 0  # cnt of files
            print(f"Processing {playlist}")
            
            json_dir = os.path.join(root_dir, playlist, 'metadata/json')
            
            for title_json in os.listdir(json_dir):
                replace_file_server(os.path.join(json_dir, title_json), old_server, new_server)
                playlist_info[playlist] += 1
    replace_file_server(os.path.join(root_dir, 'top.json'), old_server, new_server)
    return {"status": True, "msg": playlist_info}

def check_playlist(root_dir, playlist):
    playlist_dir = os.path.join(root_dir, playlist)
    json_dir = os.path.join(root_dir, playlist, "metadata", "json")
    for file in os.listdir(json_dir):
        json_file = os.path.join(json_dir, file)
        with open(json_file, 'r') as f:
            video_json = json.load(f)
        title = video_json['title']
        print(f"Checking: {title:<50s} ", end='')
        
        delete_flag = False
        encoding_del = []
        encoding_index = {}
        for encoding in video_json['encodings']:
            encoding_index[encoding['name']] = encoding
            
            resolution_del = []
            resolution_index = {}
            for src in encoding['videoSources']:
                resolution_index[src['resolution']] = src
                video_path = os.path.join(playlist_dir, f"{title} - {encoding['name']} {src['resolution']}p{video_json['ext']}")
                if not os.path.exists(video_path):
                    delete_flag = True
                    print(f"{encoding['name']} {src['resolution']}p, not exist")
                    resolution_del.append(src['resolution'])
            for resolution in resolution_del:
                encoding['videoSources'].remove(resolution_index[resolution])
            
            # check empty
            if not encoding['videoSources']:
                print(f"{encoding['name']} empty")
                encoding_del.append(encoding['name'])
        for encoding in encoding_del:
            video_json['encodings'].remove(encoding_index[encoding])
        
        if not delete_flag:
            print("exist")
        
        if not video_json['encodings']:
            # delete title
            print(f"Delete empty {title}")
            delete_title(root_dir, playlist, title)
        else:
            with open(json_file, 'w') as f:
                json.dump(video_json, f, indent=4, ensure_ascii=False)
        
    return {"status": True, "msg": "success"}

def scan_playlist(root_dir, server, playlist, title=None, screenType='flat', stereoMode='sbs', thumbnail_start_time=-1, force_thumbnail=0):
    playlist_dir = os.path.join(root_dir, playlist)
    
    # re read current id
    db_json = read_db_json(root_dir)
    current_video_id = get_current_id(db_json)
    
    # prepare dir
    thumbnail_dir = os.path.join(playlist_dir, 'metadata', 'thumbnail')
    preview_dir = os.path.join(playlist_dir, 'metadata', 'preview')
    seeklookup_dir = os.path.join(playlist_dir, 'metadata', 'seeklookup')
    json_dir = os.path.join(playlist_dir, 'metadata', 'json')
    make_dirs(thumbnail_dir, preview_dir, seeklookup_dir, json_dir, exist_ok=True)
    
    # scan playlist_dir
    if title:
        video_files = glob.glob(os.path.join(playlist_dir, glob.escape(title)+"*"))
    else:
        video_files = list(os.listdir(playlist_dir))
    
    for i, video_file in enumerate(video_files):
        # skip not video files
        video_name, ext = os.path.splitext(video_file)
        if ext not in ['.mp4', '.mkv']:
            continue
        
        # get title
        # wheather filename contains encoding and quality
        video_path = os.path.join(playlist_dir, video_file)
        is_probed = False
        m = re.search(r'(?P<title>.*?)\ -\ (?P<encoding>\w+)\ (?P<quality>\w+)\.(?P<ext>\w+)', video_file)
        if m:
            title = m.group('title')  # different encoding is seen as same title
            req_encoding = m.group('encoding')
            quality = m.group('quality')
            req_resolution = int(quality[:-1]) # 1080p -> 1080
        else:
            title = video_name
            is_probed = True
            meta_data = ffmpeg_probe(video_path)
            video_path_fixed = os.path.join(playlist_dir, f"{title} - {meta_data['encoding']} {meta_data['resolution']}p{ext}")
            os.rename(video_path, video_path_fixed)
            video_path = video_path_fixed
            
            req_encoding = meta_data['encoding']
            req_resolution = meta_data['resolution']
        
        print(f"Processing {i+1:3d}/{len(video_files):<3d}\t {title}")
        
        def probe_and_create():
            if not is_probed:
                meta_data = ffmpeg_probe(video_path)
            
            video_json = create_video_json(root_dir, server, playlist, title, video_path, meta_data, screenType=screenType, stereoMode=stereoMode, current_video_id=current_video_id)
            
            return meta_data, video_json
        
        json_file = os.path.join(root_dir, playlist, 'metadata/json', f"{title}.json")
        if not os.path.exists(json_file):
            print(f"Create New video json: {title}")
            
            meta_data, video_json = probe_and_create()
        
            # make thumbnail etc.
            thumbnailUrl, videoPreview, videoThumbnail, timelinePreview = make_thumbnail(root_dir, server, video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data, screenType=screenType, stereoMode=stereoMode, thumbnail_start_time=thumbnail_start_time, force_thumbnail=force_thumbnail)
            video_json.update({
                "videoThumbnail": videoThumbnail,
                "thumbnailUrl": thumbnailUrl,
                "videoPreview": videoPreview,
                "timelinePreview": timelinePreview,
            })
            # create video json file
            write_video_json(root_dir, playlist, title, video_json)
            # update db json
            db_json = read_db_json(root_dir)
            db_add_title(db_json, playlist, video_json)
            current_video_id += 1
            current_id_inc(db_json)
            write_db_json(root_dir, db_json)
        else:
            # read existing json
            with open(json_file, 'r') as f:
                video_json_ori = json.load(f)

            # update thumbnail
            if force_thumbnail:
                meta_data = ffmpeg_probe(video_path)
                thumbnailUrl, videoPreview, videoThumbnail, timelinePreview = make_thumbnail(root_dir, video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data, screenType=screenType, stereoMode=stereoMode, thumbnail_start_time=thumbnail_start_time, force_thumbnail=force_thumbnail)
                video_json_ori.update({
                    "videoThumbnail": videoThumbnail,
                    "thumbnailUrl": thumbnailUrl,
                    "videoPreview": videoPreview,
                    "timelinePreview": timelinePreview,
                })
                write_video_json(root_dir, playlist, title, video_json_ori)
            
            exist_flag = check_encoding(video_json_ori['encodings'], req_encoding, req_resolution)
            if exist_flag==0:
                print(f"Encoding and res Already exists, skip")
                continue
            
            # new format
            meta_data, video_json = probe_and_create()
            add_encoding(video_json_ori['encodings'], video_json['encodings'][0]['name'], video_json['encodings'][0]['videoSources'][0])
            
            # only update video json, db json don't change
            write_video_json(root_dir, playlist, title, video_json_ori)
        
    return {"status": True, "msg": "success"}

'''helper functions
'''

def db_del_playlist(db_json, playlist):
    scene_index = get_scene_index(db_json)
    if playlist in scene_index:
        db_json['scenes'].remove(scene_index[playlist])
        return True
    return False

def db_add_playlist(db_json, playlist):
    db_json['scenes'].append({
        'name': playlist,
        'list': []
    })

def db_del_title(db_json, playlist, title):
    scene_index = get_scene_index(db_json)
    title_index = get_title_index(scene_index[playlist])
    if title in title_index:
        scene_index[playlist]['list'].remove(title_index[title])
        return True
    return False

def db_add_title(db_json, playlist, video_json):
    title = video_json['title']
    short_video_json = {
        'title': video_json['title'],
        'vidoeLength': video_json['videoLength'],
        'video_url': video_json['video_url'],
        'thumbnail_url': video_json['thumbnailUrl'],
    }
    
    # new scene
    scene_index = get_scene_index(db_json)
    if playlist not in scene_index:
        db_json['scenes'].append({
            'name': playlist,
            'list': [short_video_json]
        })
        db_json['current_id'] += 1
        return True
    
    title_index = get_title_index(scene_index[playlist])
    if title not in title_index:
        scene_index[playlist]['list'].append(short_video_json)
        db_json['current_id'] += 1
        return True
    return False

def check_encoding(encodings, encoding, resolution):
    if len(encodings)==0:
        return 3 # not exist same title video
    encoding_index = {}
    for e in encodings:
        encoding_index[e['name']] = e
    
    if encoding not in encoding_index:
        return 2 # new encoding
    
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
    
    for s in encoding_index[encoding]['videoSources']:
        if s['resolution'] == videoSource['resolution']:
            return 0 # already exists
    e['videoSources'].append(videoSource)
    return 1 # same encoding, new resolution

def replace_file_playlist(json_path, src_playlist, dst_playlist):
    with open(json_path, "r") as f:
        json_text = f.read()
    json_text_new = re.sub(rf'/{src_playlist}/', f'/{dst_playlist}/', json_text)
    with open(json_path, "w") as f:
        f.write(json_text_new)
    return json_text_new

def replace_file_server(json_path, server, replace_server):
    def strip_end_slash(s):
        if s.endswith('/'):
            return s[:-1]
        return s

    with open(json_path) as f:
        text = f.read()
    new_text = text.replace(strip_end_slash(server), strip_end_slash(replace_server))
    with open(json_path, 'w') as f:
        f.write(new_text)
    return new_text

def delete_title_files(root_dir, playlist, title):
    def del_files(src_dir, title):
        files = glob.glob(os.path.join(src_dir, glob.escape(title)+"*"))
        for file in files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"{e}")
        return len(files)
    
    # remove video
    del_files(os.path.join(root_dir, playlist), title)
    # remove metadata
    del_files(os.path.join(root_dir, playlist, "metadata", "thumbnail"), title)
    del_files(os.path.join(root_dir, playlist, "metadata", "preview"), title)
    del_files(os.path.join(root_dir, playlist, "metadata", "seeklookup"), title)
    del_files(os.path.join(root_dir, playlist, "metadata", "json"), title)

def move_title_files(root_dir, src_playlist, dst_playlist, title):
    def move_files(src_dir, dst_dir, title):
        files = glob.glob(os.path.join(src_dir, glob.escape(title)+"*"))
        for file in files:
            try:
                shutil.move(file, dst_dir)
            except Exception as e:
                print(f"{e}")
        return len(files)
    
    # move video
    move_files(os.path.join(root_dir, src_playlist), os.path.join(root_dir, dst_playlist), title)
    # move metadata
    move_files(os.path.join(root_dir, src_playlist, "metadata", "thumbnail"), os.path.join(root_dir, dst_playlist, "metadata", "thumbnail"), title)
    move_files(os.path.join(root_dir, src_playlist, "metadata", "preview"), os.path.join(root_dir, dst_playlist, "metadata", "preview"), title)
    move_files(os.path.join(root_dir, src_playlist, "metadata", "seeklookup"), os.path.join(root_dir, dst_playlist, "metadata", "seeklookup"), title)
    move_files(os.path.join(root_dir, src_playlist, "metadata", "json"), os.path.join(root_dir, dst_playlist, "metadata", "json"), title)

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

def make_thumbnail(root_dir, server, video_path, thumbnail_dir, preview_dir, seeklookup_dir, title, meta_data, screenType='flat', stereoMode='sbs', thumbnail_start_time=-1, force_thumbnail=0):
    thumbnail_file = os.path.join(thumbnail_dir, f"{title}_thumbnail.jpg")
    videoPreview_file = os.path.join(preview_dir, f"{title}_preview.mp4")
    videoThumbnail_file = os.path.join(seeklookup_dir, f"{title}_seek.mp4")
    timelinePreview_file = os.path.join(seeklookup_dir, f"{title}_4096_timelinePreview341x195.jpg")  # 4096_timelinePreview341x195
    
    thumbnailUrl = f"{server}/{urllib.parse.quote(os.path.relpath(thumbnail_file, root_dir))}"
    videoPreview = f"{server}/{urllib.parse.quote(os.path.relpath(videoPreview_file, root_dir))}"
    videoThumbnail = f"{server}/{urllib.parse.quote(os.path.relpath(videoThumbnail_file, root_dir))}"
    timelinePreview = f"{server}/{urllib.parse.quote(os.path.relpath(timelinePreview_file, root_dir))}"
    
    def get_scale_str(video_width, video_height, crop_width, crop_height):
        scale_str = f"scale=-1:{crop_height},crop={crop_width}:{crop_height}"
        if video_width / video_height < crop_width / crop_height:
            scale_str = f"scale={crop_width}:-1,crop={crop_width}:{crop_height}"
        return scale_str

    width = meta_data['width']
    height = meta_data['height']
    crop_half_str = ""
    if stereoMode == 'sbs':
        crop_half_str = 'crop=iw/2:ih:0:0,'
        width //= 2
    elif stereoMode == 'tb':
        crop_half_str = 'crop=iw:ih/2:0:0,'
        height //= 2
        
    overwrite_str = '-y' if force_thumbnail & 1 else '-n'
    
    '''thumbnail'''
    if not os.path.exists(thumbnail_file) \
        or force_thumbnail & 1:
        print("generating thumbnail")
        scale_str = get_scale_str(width, height, 420, 252)
        
        if thumbnail_start_time >= 0:
            start = seconds_to_hms(thumbnail_start_time)
        else:
            start = seconds_to_hms(meta_data['duration']//2)
        cmd = f"ffmpeg -ss {start} -i '{video_path}' -vframes 1 -q:v 2 -vf '{crop_half_str}{scale_str}' '{thumbnail_file}' {overwrite_str}"
        # print(cmd)
        subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
        
    '''video preview'''
    if not os.path.exists(videoPreview_file) \
        or force_thumbnail & 2:
        # 15s, crop to 330x200
        print("generating preview video")
        scale_str = get_scale_str(width, height, 330, 200)
        overwrite_str = '-y' if force_thumbnail & 2 else '-n'
        last = min(meta_data['duration'], 15)
        
        subprocess.run(f"ffmpeg -i '{video_path}' -t {last} -an -vf '{crop_half_str}{scale_str}' -c:v libx264 -crf 23 -preset ultrafast '{videoPreview_file}' {overwrite_str}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    '''seeking preivew video'''
    if not os.path.exists(videoThumbnail_file):
        videoThumbnail = ""
    # !!! obsolescent
    # print("generating seek preview video")
    # overwrite_str = '-y' if force_thumbnail & 4 else '-n'
    # fps = 5
    # subprocess.run(f"ffmpeg -i '{video_path}' -an -vf 'fps={fps},{crop_half_str}{scale_str}' -c:v libx264 -crf 23 -preset ultrafast '{videoThumbnail_file}' {overwrite_str}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    '''timeline preview'''
    if not os.path.exists(timelinePreview_file) \
        or force_thumbnail & 8:
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

def create_video_json(root_dir, server, playlist, title, video_path, meta_data, screenType="flat", stereoMode="sbs", current_video_id=1000):
    ext = os.path.splitext(video_path)[1]
    # video json file url
    video_url = f"{server}/{urllib.parse.quote(f'{playlist}/metadata/json/{title}.json')}"
    # video file url
    video_src_url = f"{server}/{urllib.parse.quote(os.path.relpath(video_path, root_dir))}"
    
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

def make_dirs(*dirs, exist_ok=False):
    for d in dirs:
        os.makedirs(d, exist_ok=exist_ok)
