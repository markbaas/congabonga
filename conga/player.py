import logging

import gi
gi.require_version('Gst', '1.0')

from gi.repository import GObject, Gst


Gst.init(None)
_GST_PLAY_FLAGS_AUDIO = 0x02
_GST_PLAY_FLAGS_SOFT_VOLUME = 0x10


class CongaPlayer(GObject.GObject):
    __gsignals__ = {
        'playing': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'next': (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        'stopped': (GObject.SIGNAL_RUN_FIRST, None, ()),
        'position-updated': (GObject.SIGNAL_RUN_FIRST, None, (int,)),
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        # This creates a playbin pipeline and using the appsrc source
        # we can feed it our stream data
        self.pipeline = Gst.ElementFactory.make("playbin", "player")
        self.pipeline.set_property("uri", "appsrc://")
        self.stream = None
        self.track = None
        self.pos = None
        self.last_pos = 0

        # When the playbin creates the appsrc source it will call
        # this callback and allow us to configure it
        self.pipeline.connect("source-setup", self.on_source_setup)
        self.pipeline.set_property(
            'flags', _GST_PLAY_FLAGS_AUDIO | _GST_PLAY_FLAGS_SOFT_VOLUME)
        self.pipeline.set_property('buffer-size', 5 << 20)  # 5MB
        self.pipeline.set_property('buffer-duration', 5 * Gst.SECOND)
        self.pipeline.connect("audio-changed", self.on_audio_changed)
        # self.pipeline.connect("about-to-finish",
        #                       lambda src: self.emit('next'))

        # Creates a bus and set callbacks to receive errors
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message::eos", self.on_eos)
        self.bus.connect("message::error", self.on_error)

        GObject.timeout_add(200, self.query_position)

    def exit(self, msg):
        self.stop()

    def on_audio_changed(self, *args):
        state = self.pipeline.get_state(4000).pending
        if self.track and state == Gst.State.PLAYING:
            self.emit('playing', self.track)

    def stop(self):
        # Stop playback and exit mainloop
        self.stream = None
        self.track = None
        self.pipeline.set_state(Gst.State.NULL)
        self.last_pos = 0

    def toggle_pause(self):
        if self.pipeline.get_state(0).state == Gst.State.PLAYING:
            self.pipeline.set_state(Gst.State.PAUSED)
        elif self.pipeline.get_state(0).state == Gst.State.PAUSED:
            self.pipeline.set_state(Gst.State.PLAYING)

    def play(self, stream, track):
        self.stop()
        self.stream = stream
        self.track = track

        # Start playback
        self.pipeline.set_state(Gst.State.PLAYING)

    def seek(self, pos):
        self.pipeline.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH, int(pos))

    def query_position(self):
        success, pos = self.pipeline.query_position(Gst.Format.TIME)
        if success:
            self.emit('position-updated', pos / Gst.MSECOND + self.last_pos)

        return True

    def on_source_setup(self, element, source):
        source.set_property('caps', Gst.Caps.from_string(
            'audio/mpeg,mpegversion=1'))
        source.set_property('format', 'time')
        source.set_property('stream-type', 'seekable')
        source.set_property('max-bytes', 1 << 20)  # 1MB
        source.set_property('min-percent', 50)

        source.connect("need-data", self.on_source_need_data)
        source.connect("seek-data", self.on_source_seek_data)
        source.connect("enough-data", self.on_source_enough_data)

    def on_source_enough_data(self, *args):
        print(args)
        print("enough is enough")

    def on_source_seek_data(self, source, pos):
        self.pos = pos
        return True

    def on_source_need_data(self, source, length):
        # Attempt to read data from the stream
        if self.pos:
            self.last_pos = self.pos
            pos = self.pos
            self.pos = None
        else:
            pos = None

        try:
            data = self.stream.send(pos)
        except StopIteration:
            source.emit("end-of-stream")
            return

        # If data is empty it's the end of stream
        if not data:
            source.emit("end-of-stream")
            # self.emit('next')
            return

        # Convert the Python bytes into a GStreamer Buffer
        # and then push it to the appsrc
        buf = Gst.Buffer.new_wrapped(data)
        r = source.emit("push-buffer", buf)

        return r == Gst.FlowReturn.OK

    def on_eos(self, bus, msg):
        # Stop playback on end of stream
        track = self.track
        self.stop()
        self.emit('next', track)

    def on_error(self, bus, msg):
        # Print error message and exit on error
        error = msg.parse_error()[1]
        logging.error(error)
