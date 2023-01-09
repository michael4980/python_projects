from chahhel_source import Handler, Source

def test_right_method_get():
    assert Handler.do_GET == Source.current_state, 'didn`t get state info'
    
def test_rught_method_post():
    path_1 = r'http://127.0.0.1:8080/switching_on/'
    path_2 = r'http://127.0.0.1:8080/turn_off/'
    if path_1:
        assert Handler.do_POST == Source.switching_on, 'wrong switching method '
    elif path_2:
        assert Handler.do_POST == Source.switching_on, 'wrong turning off method' 