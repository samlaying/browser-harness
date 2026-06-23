import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import xhs_batch as X


def test_encode_keyword():
    assert X.encode_keyword("咖啡") == "%E5%92%96%E5%95%A1"
    assert X.encode_keyword("a b") == "a%20b"
    assert X.encode_keyword("test") == "test"
