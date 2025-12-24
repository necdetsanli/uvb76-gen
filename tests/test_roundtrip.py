from uvb76_gen.crypto import CipherConfig, decrypt_from_groups, encrypt_to_groups


def test_roundtrip() -> None:
    msg = "IF YOU SOLVE THIS, EMAIL ME"
    cfg = CipherConfig(key="BUZZERKEY", mask_key="BUZZERKEY")
    groups = encrypt_to_groups(msg, cfg)
    plain = decrypt_from_groups(groups, cfg)
    assert plain == "IFYOUSOLVETHISEMAILME"
