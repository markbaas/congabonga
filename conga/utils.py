def format_time(ms):
    s = ms / 1000 % 60
    m = int(ms / 60000)
    return '%02d:%02d' % (m, s)


def convert_to_mseconds(text):
    m, s = text.split(':')
    return (int(m) * 60 + int(s)) * 1000


def add_ellipse(text, max_chars=35):
    if len(text) > max_chars:
        text = text[:max_chars] + ' ...'
    return text
