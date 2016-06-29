# -*- coding: utf-8 -*-

import glob
import logging
import os.path
import pkgutil
import sys

import jsonpickle
from gi.repository import GObject
from concurrent import futures
import configparser


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)




class Library(GObject.GObject):
    __gsignals__ = {
        'updated': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'plugins-loaded': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'search-results-changed': (GObject.SIGNAL_RUN_FIRST, None, (str,))
    }
    tracks = {}
    cache = {
        'tracks': {},
        'artists': {},
        'albums': {}
    }
    playlists = {}
    plugins = {}

    def __init__(self, config_path):
        GObject.GObject.__init__(self)

        self.library_path = os.path.join(config_path, 'library.json')
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join(config_path, 'library.cfg'))

    def load_plugins(self):
        plugins = glob.glob(os.path.join(os.path.expanduser('~'), '.local',
                                         'share', 'congabonga', 'plugins', '*py3*.whl'))
        for plugin_file in plugins:
            sys.path.append(plugin_file)

        for plugin_name in [name for _, name, is_pkg in pkgutil.iter_modules()
                            if is_pkg and name.startswith('conga') and name != "conga"]:
            plugin_mod = __import__(plugin_name)
            try:
                section = plugin_name.replace('conga', '')
                enabled = self.config.getboolean(section, 'enabled', fallback=1)
                if not enabled:
                    continue
                username = self.config.get(section, 'username', fallback='')
                password = self.config.get(section, 'password', fallback='')
                plugin = plugin_mod.Plugin(username, password)
                logger.info('Loaded plugin: %s' % plugin_name)
            except AttributeError:
                continue

            self.plugins[plugin.name] = plugin

        self.emit('plugins-loaded')

    def plugin_callback(self, name, func):
        obj = self.plugins[name]
        return getattr(obj, func)()

    def load(self):
        self.load_plugins()
        self.load_from_local()
        self.load_tracks_from_plugins()
        self.load_playlists_from_plugins()

    def load_from_local(self):
        if os.path.exists(self.library_path):
            with open(self.library_path) as f:
                library = jsonpickle.decode(f.read())
                self.tracks = library.get('tracks', {})
                self.playlists = library.get('playlists', {})
                self.emit('updated')

    def load_tracks_from_plugins(self):
        def update_tracks(future):
            for track in future.result():
                track.in_library = True
                self.tracks[track.uri] = track
            self.emit('updated')

        for name, plugin in self.plugins.items():
            future = futures.ProcessPoolExecutor(max_workers=1)\
                .submit(self.plugin_callback, name, 'get_tracks')
            future.add_done_callback(update_tracks)

    def load_playlists_from_plugins(self):
        def update_playlists(future):
            for playlist in future.result():
                self.playlists[playlist.uri] = playlist
                for track in playlist.tracks:
                    if track not in self.tracks:
                        self.tracks[track.uri] = track
            self.emit('updated')

        # for name, plugin in self.plugins.items():
        #     future = futures.ProcessPoolExecutor(max_workers=1)\
        #         .submit(self.plugin_callback, name, 'get_playlists')
        #     future.add_done_callback(update_playlists)

    def save(self):
        with open(self.library_path, 'w') as f:
            library = {'tracks': self.tracks,
                       'playlists': self.playlists}
            f.write(jsonpickle.encode(library))

    def get_albums(self):
        """
        Gets all albums from tracks in library
        """
        names = []
        albums = []
        for uri, track in self.tracks.items():
            if track.album.name not in names:
                albums.append(track.album)
                names.append(track.album.name)

        albums.sort(key=lambda x: x.name)

        return albums

    def get_albums_from_cache(self):
        albums = [album for uri, album in self.cache['albums'].items()]
        albums.sort(key=lambda x: x.name)
        return albums

    def get_album(self, album_uri):
        for album in self.get_albums() + self.get_albums_from_cache():
            if album.uri == album_uri:
                return album

    def query_tracks(self, album=None, artist=None, include_cache=False):
        """
        Gets tracks from preloaded library
        """
        all_tracks = dict(self.tracks)
        if include_cache:
            all_tracks.update(self.cache['tracks'])

        tracks = [track for uri, track in all_tracks.items()
                  if (album is not None and track.album.uri == album) or
                  (artist is not None and track.artists[0].uri == artist)
                  ]
        tracks.sort(key=lambda x: x.track_number)
        return tracks

    def get_playlists(self):
        return self.playlists

    def get_artists(self):
        """
        Gets all artists from library
        """
        names = []
        artists = []
        for uri, track in self.tracks.items():
            if track.album.artist.name not in names and track.album.artist.name:
                artists.append(track.album.artist)
                names.append(track.album.artist.name)

        artists.sort(key=lambda x: x.name)
        return artists

    def get_artists_from_cache(self):
        artists = [artist for uri, artist in self.cache['artists'].items()]
        artists.sort(key=lambda x: x.name)
        return artists

    def get_artist(self, artist_uri):
        for artist in self.get_artists() + self.get_artists_from_cache():
            if artist.uri == artist_uri:
                return artist

    def get_track(self, track_uri):
        """
        Gets track from library of cache
        """
        track = self.tracks.get(track_uri, self.cache['tracks'].get(track_uri))
        return track

    def get_stream(self, track_uri):
        track = self.get_track(track_uri)
        try:
            plugin = self.plugins[track_uri.split(':')[0]]
        except IndexError:
            logger.error("Cannot stream %s, plugin might been disabled." % track)

        stream = plugin.stream(track)
        return stream

    def _search(self, keywords, source, matches):
        presults = {'artists': {}, 'albums': {}, 'tracks': {}}
        for plugin in self.plugins:
            if plugin == source or source == 'all':
                r = self.plugins[plugin].search(keywords, matches)
                for artist in r.get('artists', []):
                    presults['artists'][artist.uri] = artist
                for album in r.get('albums', []):
                    presults['albums'][album.uri] = album
                for track in r.get('tracks', []):
                    presults['tracks'][track.uri] = track
        return presults

    def search(self, *args, **kwargs):
        callback = kwargs.pop('on_complete')

        def on_complete(future):
            self.cache = future.result()
            GObject.idle_add(callback, self.cache)

        future = futures.ProcessPoolExecutor(max_workers=1)\
            .submit(self._search, *args)
        future.add_done_callback(on_complete)

    def do_updated(self):
        self.save()

    def fetch_tracks(self, album=None, artist=None):
        """
        Fetches tracks from api and saves them in cache
        """
        print('fetch')
        if not album and not artist:
            return

        plugin = self.plugins.get((album or artist).split(':')[0])
        if not plugin:
            return

        tracks = []
        if album:
            tracks += plugin.get_tracks(album=album)

        if artist:
            tracks = plugin.get_tracks(artist=artist)

        for track in tracks:
            self.cache['tracks'][track.uri] = track

    def add_album(self, album_uri):
        """
        Adds new album to library
        """
        tracks = self.query_tracks(album=album_uri, include_cache=True)
        for track in tracks:
            self.tracks[track.uri] = track

        self.emit('updated')

    def remove_album(self, album_uri):
        """
        Removes an album to library
        """
        # TODO: this is still tricky, as it will be overrided again by providers user tracks
        pass
