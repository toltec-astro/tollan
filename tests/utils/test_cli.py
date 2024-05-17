from tollan.utils.cli import dict_from_cli_args, split_cli_args


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


def test_split_cli_args():
    args = [
        "--a.0.b",
        "--a.0.c",
        "value",
        "--a.+0",
        '{"p": "q"}',
        "v0",
        "--a.0.d",
        "--",
        "v1",
    ]

    m, n = split_cli_args(r"a\.0\..+", args)

    assert m == ["--a.0.b", "--a.0.c", "value", "--a.0.d"]
    assert n == [
        "--a.+0",
        '{"p": "q"}',
        "v0",
        "--",
        "v1",
    ]
