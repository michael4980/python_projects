from chahhel_source import Handler, Source

s = Source()

def test_json():
    array = ['time', 'channel', 'voltage', 'current', 'power']
    assert list(s.measure(1).keys()) == array, 'incorrect output'
