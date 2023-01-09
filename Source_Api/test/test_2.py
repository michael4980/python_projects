from chahhel_source import Handler, Source

s = Source()


def test_turn_off():
    assert s.turn_off(1) == ':OUTPut1:STATe OFF', 'wrong command'
    
def test_set_current():
    assert s.set_current(2, 15) == ':SOURce2:CURRent 15', 'incorrect output'
    
def test_set_voltage():
    assert s.set_voltage(1, 5) == ':SOURce1:VOLtage 5', 'incorrect output'
    
def test_turn_on():
    assert s.turn_on(3) == ':OUTPut3:STATe ON', 'channel didn`t activate'