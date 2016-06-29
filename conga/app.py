# -*- coding: utf-8 -*-
"""Congabonga main application file mostly ui interaction."""
import os.path
from distutils import dir_util

from gi.repository import GObject

from conga.constants import (TAB_ALBUMS, TAB_ARTIST_DETAILS, TAB_ARTISTS,
                             TAB_PLAYLISTS)
from conga.library import Library
from conga.player import CongaPlayer
from conga.ui import CongaUi


class CongaApp(object):

    pending_albumart = []

    def __init__(self):
        self.config_path = os.path.join(
            os.path.expanduser("~"), '.config', 'congabonga')
        dir_util.mkpath(self.config_path)

        self.ui = CongaUi()
        self.ui.connect('tab-changed', self.on_ui_tab_changed)
        self.ui.connect('player-seek', self.on_ui_player_seek)
        self.ui.connect('player-pause', self.on_ui_player_pause)
        self.ui.connect('player-next', self.on_ui_player_next)
        self.ui.connect('player-previous', self.on_ui_player_previous)
        self.ui.connect('player-play', self.on_ui_player_play)
        self.ui.connect('playlist-activated', self.on_ui_playlist_activated)
        self.ui.connect('artist-activated', self.on_ui_artist_activated)
        self.ui.connect('album-activated', self.on_ui_album_activated)
        self.ui.connect('search', self.on_ui_search)
        self.ui.connect('library-switch-toggled', self.on_ui_library_switch_toggled)

        self.library = Library(self.config_path)
        self.library.connect('updated', self.on_library_updated)
        self.library.connect('plugins-loaded', self.on_library_plugins_loaded)
        self.library.load()

        self.player = CongaPlayer()
        self.player.connect('playing', self.on_player_playing)
        self.player.connect('stopped', self.on_player_stopped)
        self.player.connect('next', self.on_player_next)
        self.player.connect('position-updated', self.on_player_position_updated)

    def on_library_plugins_loaded(self, library):
        self.ui.update_box_search_options_sources(self.library.plugins)

    def on_library_updated(self, library):
        self.ui.update_tabs(library.tracks)
        GObject.idle_add(self.ui.update_tab_albums, library.get_albums())

    def on_ui_tab_changed(self, ui, page, user_data):
        if page == TAB_ALBUMS:
            ui.update_tab_albums(self.library.get_albums())
        elif page == TAB_PLAYLISTS:
            ui.update_tab_playlists(self.library.get_playlists())
        elif page == TAB_ARTISTS:
            ui.update_tab_artists(self.library.get_artists())

    def on_ui_player_seek(self, ui, position):
        self.player.seek(position)

    def on_ui_player_pause(self, ui):
        self.player.toggle_pause()

    def on_ui_player_previous(self, ui):
        last_track = self.player.track
        self.on_player_previous(self.player, last_track)

    def on_ui_player_next(self, ui):
        last_track = self.player.track
        self.on_player_next(self.player, last_track)

    def on_ui_player_play(self, ui, track_uri):
        self.player.play(self.library.get_stream(track_uri), track_uri)
        track = self.library.get_track(track_uri)
        ui.update_player_state_playing(track)

    def on_ui_playlist_activated(self, ui, uri):
        playlist = self.library.get_playlists()[uri]
        ui.update_playlist_details(playlist)

    def on_ui_artist_activated(self, ui, uri, from_search):
        if from_search:
            self.library.fetch_tracks(artist=uri)
            page = TAB_ARTIST_DETAILS
        else:
            page = TAB_ARTISTS

        artist = self.library.get_artist(uri)
        tracks = self.library.query_tracks(artist=uri, include_cache=from_search)
        tracks.sort(key=lambda x: (x.album.name, x.track_number))
        ui.update_tab_artist_details(artist, tracks, page=page)

    def on_ui_album_activated(self, ui, uri, from_search):
        if from_search:
            self.library.fetch_tracks(album=uri)

        tracks = self.library.query_tracks(album=uri, include_cache=from_search)
        album = self.library.get_album(uri)
        ui.update_tab_album_details(album, tracks)

    def on_ui_search(self, ui, keywords, sources, match):
        self.library.search(keywords, sources, match, on_complete=self.ui.update_search_results)

    def on_ui_library_switch_toggled(self, ui, uri, state):
        if state:
            self.library.add_album(uri)
        else:
            self.library.remove_album(uri)

    def on_player_playing(self, player, track_uri):
        track = self.library.get_track(track_uri)
        self.ui.update_player_state_playing(track)

    def on_player_stopped(self, player):
        self.ui.update_player_state_stopped()

    def on_player_next(self, player, track_uri):
        next_uri = self.ui.get_playlist_next(track_uri)
        if next_uri:
            self.player.play(self.library.get_stream(next_uri), next_uri)
            track = self.library.get_track(track_uri)
            self.ui.update_player_state_playing(track)

    def on_player_previous(self, player, track_uri):
        next_uri = self.ui.get_playlist_next(track_uri, n=-1)
        if next_uri:
            self.player.play(self.library.get_stream(next_uri), next_uri)
            track = self.library.get_track(track_uri)
            self.ui.update_player_state_playing(track)

    def on_player_position_updated(self, player, position):
        self.ui.update_scale(position)
