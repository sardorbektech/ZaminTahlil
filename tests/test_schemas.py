import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest


def test_chat_message_contract() -> None:
    valid = ChatRequest(messages=[{"role": "user", "content": str(index)} for index in range(10)])
    assert len(valid.messages) == 10
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": str(index)} for index in range(11)])

    # Assistant rolli xabarlarga ruxsat beriladi — frontend suhbat tarixini yuboradi.
    accepted = ChatRequest(messages=[{"role": "assistant", "content": "ok"}])
    assert accepted.messages[0].role == "assistant"

    # Frontend tili ixtiyoriy, lekin faqat ruxsat etilgan qiymatlar.
    assert ChatRequest(
        messages=[{"role": "user", "content": "salom"}], language="ru"
    ).language == "ru"
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "user", "content": "salom"}], language="de")

    # Noto'g'ri role rad etiladi.
    with pytest.raises(ValidationError):
        ChatRequest(messages=[{"role": "system", "content": "not allowed"}])


def test_database_has_no_persistent_chat_table(repository) -> None:
    with repository.database.connect() as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "chat" not in names and "messages" not in names
