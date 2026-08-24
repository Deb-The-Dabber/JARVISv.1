"""Unit tests for email IMAP tools (no network, mock IMAP)."""

import email
import imaplib
from unittest.mock import MagicMock, patch

import pytest

import tools.email_tools as et

# (DEFAULT_FOLDER, FETCH_BODY, HOST, PORT, SSL, MAX_RESULTS, PASSWORD, USERNAME)
TEST_CONFIG = ("INBOX", True, "imap.gmail.com", 993, True, 20, "test_password", "test@example.com")


@pytest.fixture(autouse=True)
def fake_config(monkeypatch):
    monkeypatch.setattr(et, "_get_config", lambda: TEST_CONFIG)


# ─────────────────────────────────────────────
# Header decoding tests
# ─────────────────────────────────────────────


def test_decode_header_plain():
    assert et._decode_header("simple") == "simple"
    assert et._decode_header("") == ""


def test_decode_header_mime_encoded():
    encoded = "=?utf-8?q?Hello_World?="
    assert et._decode_header(encoded) == "Hello World"


def test_decode_header_multiple_parts():
    # RFC 2047: whitespace between adjacent encoded-words is not significant,
    # so stdlib decodes these to a single merged word.
    encoded = "=?utf-8?q?Hello?= =?utf-8?q?World?="
    assert et._decode_header(encoded) == "HelloWorld"


def test_format_email_address():
    assert et._format_email_address("user@example.com") == "user@example.com"
    assert et._format_email_address("John Doe <john@example.com>") == "John Doe <john@example.com>"
    assert et._format_email_address("") == ""


# ─────────────────────────────────────────────
# IMAP search criteria parsing
# ─────────────────────────────────────────────


def test_build_search_criteria_simple():
    criteria = et._build_search_criteria("FROM boss")
    assert 'FROM "boss"' in criteria[0]


def test_build_search_criteria_quoted():
    criteria = et._build_search_criteria('FROM "john doe"')
    assert 'FROM "john doe"' in criteria[0]


def test_build_search_criteria_single_quoted():
    criteria = et._build_search_criteria("SUBJECT 'weekly report'")
    assert 'SUBJECT "weekly report"' in criteria[0]


def test_build_search_criteria_multiple():
    criteria = et._build_search_criteria('FROM "boss" SUBJECT "report" UNREAD')
    assert 'FROM "boss"' in criteria
    assert 'SUBJECT "report"' in criteria
    assert "UNREAD" in criteria


def test_build_search_criteria_empty():
    assert et._build_search_criteria("") == ["ALL"]


def test_build_search_criteria_flags():
    criteria = et._build_search_criteria("UNREAD FLAGGED")
    assert "UNREAD" in criteria
    assert "FLAGGED" in criteria


def test_build_search_criteria_date():
    criteria = et._build_search_criteria("SINCE 01-Jan-2025")
    assert 'SINCE "01-Jan-2025"' in criteria


# ─────────────────────────────────────────────
# Body extraction tests
# ─────────────────────────────────────────────


def test_get_body_simple_text():
    msg = email.message.EmailMessage()
    msg.set_content("Hello world")
    text, html = et._get_body_from_message(msg)
    assert text == "Hello world"
    assert html == ""


def test_get_body_multipart():
    msg = email.message.EmailMessage()
    msg.make_alternative()
    msg.add_alternative("Hello text", subtype="plain")
    msg.add_alternative("<p>Hello HTML</p>", subtype="html")
    text, html = et._get_body_from_message(msg)
    assert "Hello text" in text
    assert "Hello HTML" in html


def test_get_body_attachment_skipped():
    msg = email.message.EmailMessage()
    msg.make_mixed()
    text_part = email.message.EmailMessage()
    text_part.set_content("Body text")
    msg.attach(text_part)
    attachment = email.message.EmailMessage()
    attachment.set_content("Attachment content")
    attachment.add_header("Content-Disposition", "attachment", filename="test.txt")
    msg.attach(attachment)
    text, html = et._get_body_from_message(msg)
    assert "Body text" in text
    assert "Attachment content" not in text


# ─────────────────────────────────────────────
# Exception hierarchy + config helpers
# ─────────────────────────────────────────────


def test_exception_hierarchy():
    assert issubclass(et.EmailAuthError, et.EmailError)
    assert issubclass(et.EmailConnectionError, et.EmailError)
    assert issubclass(et.EmailFolderError, et.EmailError)
    assert issubclass(et.EmailMessageError, et.EmailError)


def test_get_default_folder():
    assert et._get_default_folder() == "INBOX"


def test_get_max_results():
    assert et._get_max_results() == 20


def test_get_fetch_body():
    assert et._get_fetch_body() is True


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.setattr(et, "_get_config", lambda: ("INBOX", True, "imap.gmail.com", 993, True, 20, "", ""))
    with pytest.raises(et.EmailAuthError):
        et._get_imap_connection()


# ─────────────────────────────────────────────
# Integration tests (mocked IMAP)
# ─────────────────────────────────────────────

HDR_1 = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Cc: cc@example.com\r\n"
    b"Subject: Test Subject\r\n"
    b"Date: Thu, 1 Jan 2025 10:00:00 +0000\r\n\r\n"
)
HDR_2 = (
    b"From: sender2@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Subject: Another Subject\r\n"
    b"Date: Thu, 1 Jan 2025 11:00:00 +0000\r\n\r\n"
)
ENV_1 = b'(FLAGS (\\Seen) ENVELOPE ("1-Jan-2025" "Test Subject" NIL NIL NIL NIL NIL NIL NIL NIL))'
ENV_2 = b'(FLAGS () ENVELOPE ("1-Jan-2025" "Another Subject" NIL NIL NIL NIL NIL NIL NIL NIL))'


def make_mock_conn():
    mock_conn = MagicMock()
    mock_conn.select.return_value = ("OK", [b"1 2 3 4 5"])
    return mock_conn


def fetch_header_side_effect(*args):
    uid = args[0]
    if uid == b"2":
        return ("OK", [(b"2", HDR_2)])
    return ("OK", [(b"1", HDR_1)])


def check_email_fetch_side_effect(*args):
    uid = args[0]
    cmd = args[1]
    if "ENVELOPE" in cmd:
        return ("OK", [(uid, ENV_2 if uid == b"2" else ENV_1)])
    return ("OK", [(uid, HDR_2 if uid == b"2" else HDR_1)])


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_check_email_success(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.side_effect = check_email_fetch_side_effect

    result = et.check_email()
    assert "Test Subject" in result
    assert "sender@example.com" in result
    assert "Another Subject" in result


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_check_email_unread_only(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.search.return_value = ("OK", [b""])

    result = et.check_email(unread_only=True)
    assert "No unread emails" in result
    mock_conn.search.assert_called_once_with(None, "UNSEEN")


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_read_email_success(mock_imap_ssl):
    msg = email.message.EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Test Subject"
    msg["Date"] = "Thu, 1 Jan 2025 10:00:00 +0000"
    msg["Message-ID"] = "<test@example.com>"
    msg.set_content("Hello world")

    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

    result = et.read_email("1")
    assert "sender@example.com" in result
    assert "Test Subject" in result
    assert "Hello world" in result


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_search_email_success(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.side_effect = fetch_header_side_effect

    result = et.search_email('FROM "boss"')
    assert "sender@example.com" in result
    assert "Test Subject" in result
    args, _ = mock_conn.search.call_args
    assert args[0] is None
    assert 'FROM "boss"' in args[1]


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_list_folders_success(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.list.return_value = (
        "OK",
        [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent"'],
    )

    result = et.list_folders()
    assert "INBOX" in result
    assert "Sent" in result


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_get_email_summary_success(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.search.side_effect = [
        ("OK", [b"1 2 3 4 5"]),  # ALL
        ("OK", [b"1 2"]),  # UNSEEN
        ("OK", [b"4 5"]),  # SINCE
        ("OK", [b"4 5"]),  # SINCE (top senders)
    ]
    mock_conn.fetch.side_effect = fetch_header_side_effect

    result = et.get_email_summary()
    assert "Total messages: 5" in result
    assert "Unread: 2" in result
    assert "sender@example.com" in result


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_auth_error(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.login.side_effect = imaplib.IMAP4.error("auth failed")

    with pytest.raises(et.EmailAuthError):
        et.check_email()


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_connection_error(mock_imap_ssl):
    mock_imap_ssl.side_effect = Exception("connection refused")

    with pytest.raises(et.EmailConnectionError):
        et.check_email()


@patch("tools.email_tools.imaplib.IMAP4_SSL")
def test_folder_not_found(mock_imap_ssl):
    mock_conn = make_mock_conn()
    mock_imap_ssl.return_value = mock_conn
    mock_conn.select.return_value = ("NO", [b"Folder not found"])

    with pytest.raises(et.EmailFolderError):
        et.check_email(folder="NonExistent")
