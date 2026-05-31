from cratedig.audio.category import classify_category


def test_classify_category_from_filename():
    assert classify_category("/packs/kicks/dirty_kick_01.wav") == "kick"
    assert classify_category("/packs/vocals/short_vox.wav") == "vocal"
    assert classify_category("/packs/fx/big_riser.wav") == "fx"


def test_classify_category_from_folder_name():
    assert classify_category("/packs/Basses/clean_01.wav") == "bass"


def test_classify_category_unknown():
    assert classify_category("/packs/misc/texture.wav") is None
