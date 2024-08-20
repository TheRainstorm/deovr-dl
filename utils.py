import argparse
import glob
import json
import re
import os
import shutil

from generate_json import add_to_top_json, read_top_json, write_top_json, del_top_json

def get_scene_index(top_json):
    scene_index = {}
    for scene in top_json['scenes']:
        scene_index[scene['name']] = scene
    return scene_index

def get_title_index(scene):
    title_index = {}
    for video_json in scene['list']:
        title_index[video_json['title']] = video_json
    return title_index

def db_del_playlist(top_json, playlist):
    scene_index = get_scene_index(top_json)
    if playlist in scene_index:
        top_json['scenes'].remove(scene_index[playlist])
        return True
    return False

def db_add_playlist(top_json, playlist):
    top_json['scenes'].append({
        'name': playlist,
        'list': []
    })

def db_del_title(top_json, playlist, title):
    scene_index = get_scene_index(top_json)
    title_index = get_title_index(scene_index[playlist])
    if title in title_index:
        scene_index[playlist]['list'].remove(title_index[title])
        return True
    return False

def db_add_title(top_json, playlist, video_json):
    title = video_json['title']
    short_video_json = {
        'title': video_json['title'],
        'vidoeLength': video_json['videoLength'],
        'video_url': video_json['video_url'],
        'thumbnail_url': video_json['thumbnailUrl'],
    }
    
    # new scene
    scene_index = get_scene_index(top_json)
    if playlist not in scene_index:
        top_json['scenes'].append({
            'name': playlist,
            'list': [short_video_json]
        })
        top_json['current_id'] += 1
        return True
    
    title_index = get_title_index(scene_index[playlist])
    if title not in title_index:
        scene_index[playlist]['list'].append(short_video_json)
        top_json['current_id'] += 1
        return True
    return False

def clean_title_files(root_dir, playlist, title):
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

'''API functions
'''
def print_db_info(root_dir):
    top_json = read_top_json(root_dir)
    scene_index = get_scene_index(top_json)
    print("Playlists:")
    for scene_name, scene in scene_index.items():
        print(f"{scene_name}: {len(scene['list'])}")

def move_title_from_to(root_dir, src_playlist, dst_playlist, title):
    top_json = read_top_json(root_dir)
    scene_index = get_scene_index(top_json)
    if src_playlist not in scene_index or dst_playlist not in scene_index:
        print(f"Playlist {src_playlist} or {dst_playlist} not found")
        return False
    
    # update json
    json_path = os.path.join(args.root_dir, src_playlist, "metadata", "json", f"{title}.json")
    with open(json_path, "r") as f:
        json_text = f.read()
    json_text_new = re.sub(rf'/{src_playlist}/', f'/{dst_playlist}/', json_text)
    with open(json_path, "w") as f:
        f.write(json_text_new)
    video_json = json.loads(json_text_new)
    
    # move files
    move_title_files(args.root_dir, src_playlist, dst_playlist, title)
    
    # update db
    top_json = read_top_json(root_dir)
    db_del_title(top_json, src_playlist, title)
    db_add_title(top_json, dst_playlist, video_json)
    write_top_json(root_dir, top_json)
    return True

def rename_playlist(root_dir, src_playlist, dst_playlist):
    top_json = read_top_json(root_dir)
    scene_index = get_scene_index(top_json)
    if dst_playlist in scene_index:
        print(f"Playlist {dst_playlist} already exists")
        return False
    
    # rename playlist dir
    os.rename(os.path.join(root_dir, src_playlist), os.path.join(root_dir, dst_playlist))
    
    # update json files
    json_dir = os.path.join(root_dir, dst_playlist, "metadata", "json")
    for file in os.listdir(json_dir):
        if file.endswith(".json"):
            title, ext = os.path.splitext(file)
            json_path = os.path.join(json_dir, file)
            with open(json_path, "r") as f:
                json_text = f.read()
            json_text_new = re.sub(rf'/{src_playlist}/', f'/{dst_playlist}/', json_text)
            with open(json_path, "w") as f:
                f.write(json_text_new)
    
    # update db
    scene_index[src_playlist]['name'] = dst_playlist
    write_top_json(root_dir, top_json)

parser = argparse.ArgumentParser(description='DeoVR video library tool')
parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
# parser.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')

subparsers = parser.add_subparsers(title="command", dest="command")

# move
parser_move = subparsers.add_parser("move", help="move playlist to another playlist")
parser_move.add_argument("--src", required=True, help="from playlist")
parser_move.add_argument("--dst", required=True, help="to playlist")
parser_move.add_argument('-V', '--title', help='only move one video title')

# dupdel
parser_dupdel = subparsers.add_parser("dupdel", help="delete duplicate videos")
parser_dupdel.add_argument("--src", required=True, help="clean dup")
parser_dupdel.add_argument("--ref", required=True, help="used to compare")

# rename
parser_rename = subparsers.add_parser("rename", help="rename playlist")
parser_rename.add_argument("--src", required=True, help="old name")
parser_rename.add_argument("--dst", required=True, help="new name")

# list
parser_list = subparsers.add_parser("list", help="list playlist info")

args = parser.parse_args()

if args.command == "move":
    title_list = []
    if args.title:
        title_list = [args.title]
    else:
        top_json = read_top_json(args.root_dir)
        scene_index = get_scene_index(top_json)
        if args.src not in scene_index or args.dst not in scene_index:
            print(f"Playlist {args.src} or {args.dst} not found")
            exit(1)
        title_index = get_title_index(scene_index[args.src])
        title_list = list(title_index.keys())
    
    for title in title_list:
        print(f"Moving {title}")
        move_title_from_to(args.root_dir, args.src, args.dst, title)
    
    # remove playlist in db
    top_json = read_top_json(args.root_dir)
    db_del_playlist(top_json, args.src)
    write_top_json(args.root_dir, top_json)
    
    # remove playlist dir
    # input(f"Remove {args.src} playlist? Press Enter to continue...")
    print(f"Remove {args.src} playlist")
    shutil.rmtree(os.path.join(args.root_dir, args.src))
    
elif args.command == "dupdel":
    top_json = read_top_json(args.root_dir)
    scene_index = get_scene_index(top_json)
    title_index_src = get_title_index(scene_index[args.src])
    title_index_ref = get_title_index(scene_index[args.ref])
    for title in title_index_src:
        if title in title_index_ref:
            print(f"Delete {title}", end=" ")
            clean_title_files(args.root_dir, args.src, title)
            succ = db_del_title(top_json, args.src, title)
            print("Succ" if succ else "Failed")
            write_top_json(args.root_dir, top_json)

elif args.command == "rename":
    rename_playlist(args.root_dir, args.src, args.dst)
elif args.command == "list":
    print_db_info(args.root_dir)
else:
    print("Not implemented")
    exit(1)
