import argparse
import os
import shutil

from db_utils import *

parser = argparse.ArgumentParser(description='DeoVR database json manipulate tool')
parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
subparsers = parser.add_subparsers(title="command", dest="command")

# list
parser_list = subparsers.add_parser("list", help="list playlist info")
parser_list.add_argument('-P', '--playlist', help='list specific playlist')
parser_list.add_argument('-a', '--all', action='store_true', help='list all videos')
parser_list.add_argument('-m', '--multi-format', action='store_true', help='list video with multi-format')

# change server address
parser_change = subparsers.add_parser("change", help="change server address")
parser_change.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')
parser_change.add_argument('-R', '--replace-server', default="http://localhost:8000", help='New HTTP server address will replace')

# rename
parser_rename = subparsers.add_parser("rename", help="rename playlist")
parser_rename.add_argument("--src", required=True, help="old name")
parser_rename.add_argument("--dst", required=True, help="new name")

# move
parser_move = subparsers.add_parser("move", help="move playlist to another playlist")
parser_move.add_argument("--src", required=True, help="from playlist")
parser_move.add_argument("--dst", required=True, help="to playlist")
parser_move.add_argument('-V', '--title', help='only move one video title')

# dupdel
parser_dupdel = subparsers.add_parser("dupdel", help="delete duplicate videos")
parser_dupdel.add_argument("--src", required=True, help="clean dup")
parser_dupdel.add_argument("--ref", required=True, help="used to compare")

# check
parser_check = subparsers.add_parser("check", help="Scan directory, clean not exist video encoding in json")
parser.add_argument('-P', '--playlist', help='check specific playlist, default clean all playlists')

# scan
parser_scan = subparsers.add_parser("scan", help="Scan directory, ")
parser_scan.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')
parser_scan.add_argument('-P', '--playlist', help='update specific playlist, or scan all playlists')
parser_scan.add_argument('-t', '--title', help='Scan video start with title')
parser_scan.add_argument('--screenType', default="flat", help='flat, dome(180), sphere(360)')
parser_scan.add_argument('--stereoMode', default="sbs", help='sbs, tb')
parser_scan.add_argument('-s', '--thumbnail-start-time', type=int, default=-1, help='specific thumbnail shot time. default shot at 1/3 duration')
parser_scan.add_argument('-F', '--force-thumbnail', type=int, default=0, help='bitmask, force regenerate video seek|video preview|thumbnail')

args = parser.parse_args()

root_dir = args.root_dir
if args.command == "list":
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    playlists = list(scene_index.keys())
    if args.playlist:
        playlists = [args.playlist]
    for playlist in playlists:
        print(f"{playlist}: ")
        title_index = get_title_index(scene_index[playlist])
        if args.all:
            for title, video in title_index.items():
                print(f"\t{title}")
        elif args.multi_format:
            for title, video in title_index.items():
                video_json = read_video_json(root_dir, playlist, title)
                formats = get_video_formats(video_json)
                if len(formats) > 1:
                    print(f"\t{title}: {formats}")
        else:
            print(f"\t{len(title_index)} videos")
elif args.command == "change":
    res = change_server(root_dir, args.server, args.replace_server)
    print(res)
elif args.command == "move":
    title_list = []
    if args.title:
        title_list = [args.title]
    else:
        db_json = read_db_json(root_dir)
        scene_index = get_scene_index(db_json)
        if args.src not in scene_index or args.dst not in scene_index:
            print(f"Playlist {args.src} or {args.dst} not found")
            exit(1)
        title_index = get_title_index(scene_index[args.src])
        title_list = list(title_index.keys())
    
    for title in title_list:
        print(f"Moving {title}")
        move_title_from_to(root_dir, args.src, args.dst, title)
    
    # remove playlist in db
    db_json = read_db_json(root_dir)
    db_del_playlist(db_json, args.src)
    write_db_json(root_dir, db_json)
    
    # remove playlist dir
    # input(f"Remove {args.src} playlist? Press Enter to continue...")
    print(f"Remove {args.src} playlist")
    shutil.rmtree(os.path.join(root_dir, args.src))
    
elif args.command == "dupdel":
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    title_index_src = get_title_index(scene_index[args.src])
    title_index_ref = get_title_index(scene_index[args.ref])
    for title in title_index_src:
        if title in title_index_ref:
            print(f"Delete {title}", end=" ")
            delete_title_files(root_dir, args.src, title)
            succ = db_del_title(db_json, args.src, title)
            print("Succ" if succ else "Failed")
            write_db_json(root_dir, db_json)

elif args.command == "rename":
    rename_playlist(root_dir, args.src, args.dst)
elif args.command == "check":
    if args.playlist:
        check_playlist(root_dir, args.playlist)
    else:
        scene_index = get_scene_index(read_db_json(root_dir))
        for playlist in scene_index:
            check_playlist(root_dir, playlist)
elif args.command == "scan":
    if args.playlist:
        scan_playlist(root_dir, args.server, args.playlist, title=args.title, screenType=args.screenType, stereoMode=args.stereoMode, thumbnail_start_time=args.thumbnail_start_time, force_thumbnail=args.force_thumbnail)
    else:
        scene_index = get_scene_index(read_db_json(root_dir))
        for playlist in scene_index:
            scan_playlist(root_dir, args.server, playlist, title=args.title, screenType=args.screenType, stereoMode=args.stereoMode, thumbnail_start_time=args.thumbnail_start_time, force_thumbnail=args.force_thumbnail)
else:
    print("Not implemented")
    exit(1)
