import argparse
from flask import Flask, redirect, render_template, request, url_for
from db_utils import *

app = Flask("VRhouse", template_folder='web/templates', static_folder='web/static')
@app.route('/')
def index():
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    
    playlist_data = {}
    for scene_name, scene in scene_index.items():
        playlist_data[scene_name] = len(scene['list'])
    return render_template('index.html', playlist_data=playlist_data)

@app.route('/playlist/<playlist>')
def playlist(playlist):
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    title_index = get_title_index(scene_index[playlist])
    
    return render_template('playlist.html', title_index=title_index, playlist=playlist)

@app.route('/video/<playlist>/<title>')
def video(playlist, title):
    video = read_video_json(root_dir, playlist, title)
    
    db_json = read_db_json(root_dir)
    scene_index = get_scene_index(db_json)
    return render_template('video.html', video=video, playlist=playlist, playlists=list(scene_index.keys()))

# Ajax
@app.route('/api/delete/<playlist>/<title>')
def delete(playlist, title):
    print(f"delete {playlist}/{title}")
    return delete_title(root_dir, playlist, title)

@app.route('/api/move', methods=['POST'])
def move():
    src_playlist = request.form.get('src_playlist')
    dst_playlist = request.form.get('dst_playlist')
    title = request.form.get('title')
    return move_title_from_to(root_dir, src_playlist, dst_playlist, title)
    # return redirect(url_for('playlist', playlist=src_playlist))

@app.route('/api/rename/<src_playlist>/<dst_playlist>')
def rename(src_playlist, dst_playlist):
    return rename_playlist(root_dir, src_playlist, dst_playlist)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
    parser.add_argument('-l', '--listen',
                        default='localhost:8000',
                        help='Server listen address')
    args = parser.parse_args()
    # global var
    root_dir = args.root_dir
    
    # print(f"os.getcwd(): {os.getcwd()}")
    host, port = args.listen.rsplit(':', 1)
    app.run(host=host, port=int(port), debug=True)
