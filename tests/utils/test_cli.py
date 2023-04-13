from tollan.utils.cli import dict_from_cli_args


def test_dict_from_cli_args():
    args = ["--a.0.b", "--a.0.c", "value", "--a.+0", '{"p": "q"}']

    d = dict_from_cli_args(args)

    assert d == {
        "a": {
            "0": {
                "b": True,
                "c": "value",
            },
            "+0": {"p": "q"},
        },
    }
