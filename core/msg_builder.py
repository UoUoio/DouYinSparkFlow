"""
core/msg_builder.py
构建具体发送的消息内容
"""

import random
import string


def build_message() -> str:
    suffix = "".join(random.choices(string.ascii_letters, k=2))
    return f"续火花{suffix}"
