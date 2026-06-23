import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import xhs_batch as X


def test_encode_keyword():
    assert X.encode_keyword("咖啡") == "%E5%92%96%E5%95%A1"
    assert X.encode_keyword("a b") == "a%20b"
    assert X.encode_keyword("test") == "test"


def test_waterfall_sort_3col_2row():
    # 3 列 x 2 排；同排 y 差 <100
    items = [
        {'id': 'a', 'x': 196, 'y': 100}, {'id': 'b', 'x': 451, 'y': 110}, {'id': 'c', 'x': 706, 'y': 95},
        {'id': 'd', 'x': 196, 'y': 400}, {'id': 'e', 'x': 451, 'y': 410}, {'id': 'f', 'x': 706, 'y': 405},
    ]
    # 排1(y~100): 按 x 升序 a,b,c；排2(y~400): d,e,f
    assert X.waterfall_sort(items) == ['a', 'b', 'c', 'd', 'e', 'f']


def test_waterfall_sort_gap_splits_rows_and_x_within_row():
    # y 差 150 >= 100 → 两排；排内按 x 升序
    items = [
        {'id': 'a', 'x': 451, 'y': 100}, {'id': 'b', 'x': 196, 'y': 100},   # 排1 → b,a
        {'id': 'c', 'x': 451, 'y': 250}, {'id': 'd', 'x': 196, 'y': 250},   # 排2 → d,c
    ]
    assert X.waterfall_sort(items) == ['b', 'a', 'd', 'c']


def test_waterfall_sort_empty():
    assert X.waterfall_sort([]) == []


def test_compute_threads_levels_and_reply_to():
    comments = [
        {'lvl': 1, 'nick': 'Alice', 'content': 'hi'},
        {'lvl': 2, 'nick': 'Bob',   'content': 're'},      # 回复 Alice
        {'lvl': 1, 'nick': 'Carol', 'content': 'yo'},
        {'lvl': 2, 'nick': 'Dave',  'content': 're2'},     # 回复 Carol
    ]
    out = X.compute_threads(comments)
    assert out[0]['thread_id'] == 1 and out[0]['reply_to'] == ''
    assert out[1]['thread_id'] == 1 and out[1]['reply_to'] == 'Alice'
    assert out[2]['thread_id'] == 2 and out[2]['reply_to'] == ''
    assert out[3]['thread_id'] == 2 and out[3]['reply_to'] == 'Carol'


def test_compute_threads_does_not_mutate_input():
    comments = [{'lvl': 1, 'nick': 'A', 'content': 'x'}]
    X.compute_threads(comments)
    assert 'thread_id' not in comments[0]


def test_compute_threads_empty():
    assert X.compute_threads([]) == []
