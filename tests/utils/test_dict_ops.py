from tollan.utils.general import dict_from_flat_dict, dict_to_flat_dict, rupdate


def test_dict_from_flat_dict():
    fd = {"a.0.b": True, "a.1": 1, "b": "value", "a.+0": {"p": "q"}}
    d = dict_from_flat_dict(fd)
    assert d == {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}


def test_dict_to_flat_dict():
    d = {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}
    fd = dict_to_flat_dict(d)
    assert fd == {"a.0.b": True, "a.1": 1, "b": "value", "a.+0.p": "q"}


def test_rupdate():
    d = {"a": [{}, -1]}
    d1 = {"a": {"0": {"b": True}, "1": 1, "+0": {"p": "q"}}, "b": "value"}
    rupdate(d, d1)
    assert d == {"a": [{"p": "q"}, {"b": True}, 1], "b": "value"}
