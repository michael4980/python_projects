from chahhel_source import Handler, Source
from config import load_config

config = load_config('source.ini')

def test_right_method_get():
    assert Handler.do_GET == Source.current_state, 'didn`t get state info'
    
def test_rught_method_post():
    path_1 = f'{config.api_src.host}/switching_on/'
    path_2 = f'{config.api_src.host}/turn_off/'
    if path_1:
        assert Handler.do_POST == Source.switching_on, 'wrong switching method '
    elif path_2:
        assert Handler.do_POST == Source.switching_on, 'wrong turning off method' 