from lingdongvideo import VideoPlayerWindow as BaseVideoPlayerWindow


class DirectorVideoPlayer(BaseVideoPlayerWindow):
    def __init__(self, video_path, parent=None):
        super().__init__(video_path, parent)

