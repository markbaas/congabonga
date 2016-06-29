from gi.repository import GdkPixbuf, GObject, Gio, GLib
import base64
import os.path
from distutils import dir_util
import requests


def create_thumb(job, cancellable, user_data):
    url, out, updater = user_data
    data = requests.get(url).content
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
    pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
    pixbuf.savev(out, 'jpeg', [], [])
    GObject.idle_add(updater, pixbuf)


class BaseModel:
    _pixbuf = None

    @property
    def cached(self):
        cache_path = os.path.join(os.path.expanduser('~'), '.cache', 'congabonga', 'albumart')
        dir_util.mkpath(cache_path)

        b64url = base64.b64encode(self.image.encode('utf-8')).decode('utf-8')
        cached = os.path.join(cache_path, b64url)
        return cached

    def get_pixbuf(self, updater=None):
        if os.path.exists(self.cached) and self.image:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.cached)
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file('data/missing-artwork.png')
            if updater and self.image:
                Gio.io_scheduler_push_job(
                    create_thumb, (self.image, self.cached, updater), GLib.PRIORITY_DEFAULT, None)

        return pixbuf


class BaseArtist(BaseModel):
    pass


class BaseAlbum(BaseModel):

    def _get_field(self, field):
        if hasattr(self, field):
            return getattr(self, field)
        else:
            raise NotImplemented('Album "%s" field should be implemented' % field)

    @property
    def name(self):
        return self._get_field('_name')

    @property
    def uri(self):
        return self._get_field('_uri')

    @property
    def raw_date(self):
        return self._get_field('_raw_date')

    @property
    def date(self):
        return self._get_field('_date')

    @property
    def artists(self):
        return self._get_field('_artists')

    @property
    def artist(self):
        return self._get_field('_artist')

    @property
    def image(self):
        return self._get_field('_image')

    @property
    def num_tracks(self):
        return self._get_field('_num_tracks')


class BasePlayList(BaseModel):
    pass


class BaseTrack(BaseModel):
    in_library = False


class BaseTrackList(list):
    pass
