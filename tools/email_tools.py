"""Email IMAP tools — universal IMAP support for any provider (Gmail, Outlook, Yahoo, custom).

Callable-only tools: check_email, read_email, search_email, list_email_folders, get_email_summary.
No intent routing — invoked explicitly or via agent_spawn.
"""

import email
import email.header
import email.message
import email.utils
import imaplib
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def _get_config():
    """Lazy-load config to allow test patching."""
    from config import (
        EMAIL_DEFAULT_FOLDER,
        EMAIL_FETCH_BODY,
        EMAIL_IMAP_HOST,
        EMAIL_IMAP_PORT,
        EMAIL_IMAP_SSL,
        EMAIL_MAX_RESULTS,
        EMAIL_PASSWORD,
        EMAIL_USERNAME,
    )

    return (
        EMAIL_DEFAULT_FOLDER,
        EMAIL_FETCH_BODY,
        EMAIL_IMAP_HOST,
        EMAIL_IMAP_PORT,
        EMAIL_IMAP_SSL,
        EMAIL_MAX_RESULTS,
        EMAIL_PASSWORD,
        EMAIL_USERNAME,
    )


def _get_default_folder() -> str:
    return _get_config()[0]


def _get_max_results() -> int:
    return _get_config()[5]


def _get_fetch_body() -> bool:
    return _get_config()[1]


class EmailError(Exception):
    """Base exception for email-related errors."""

    pass


class EmailAuthError(EmailError):
    """Authentication failed."""

    pass


class EmailConnectionError(EmailError):
    """Connection failed."""

    pass


class EmailFolderError(EmailError):
    """Folder not found."""

    pass


class EmailMessageError(EmailError):
    """Message not found."""

    pass


def _decode_header(value: str) -> str:
    """Decode MIME encoded header value."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded_parts = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            if encoding:
                try:
                    decoded_parts.append(part.decode(encoding))
                except (UnicodeDecodeError, LookupError):
                    decoded_parts.append(part.decode("latin-1", errors="replace"))
            else:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


def _parse_imap_date(date_str: str) -> Optional[datetime]:
    """Parse IMAP date string to datetime."""
    if not date_str:
        return None
    try:
        return email.utils.parsedate_to_datetime(date_str)
    except Exception:
        return None


def _format_email_address(addr: str) -> str:
    """Format email address for display."""
    if not addr:
        return ""
    return _decode_header(addr)


def _get_body_from_message(msg: email.message.Message, include_html: bool = False) -> Tuple[str, str]:
    """Extract text and HTML body from email message."""
    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (UnicodeDecodeError, LookupError):
                decoded = payload.decode("latin-1", errors="replace")
            if content_type == "text/plain":
                text_body += decoded
            elif content_type == "text/html":
                html_body += decoded
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (UnicodeDecodeError, LookupError):
                decoded = payload.decode("latin-1", errors="replace")
            if msg.get_content_type() == "text/html":
                html_body = decoded
            else:
                text_body = decoded

    return text_body.strip(), html_body.strip()


def _build_search_criteria(query: str) -> List[str]:
    """Parse user query into IMAP SEARCH criteria.

    Supports:
    - FROM "addr" or FROM addr
    - TO "addr" or TO addr
    - SUBJECT "text" or SUBJECT text
    - BODY "text" or BODY text
    - SINCE "DD-MMM-YYYY" or SINCE DD-MMM-YYYY
    - BEFORE "DD-MMM-YYYY" or BEFORE DD-MMM-YYYY
    - UNREAD / SEEN / FLAGGED / UNANSWERED / DELETED / DRAFT

    Multiple criteria are ANDed together.
    """
    if not query or not query.strip():
        return ["ALL"]

    criteria = []
    tokens = query.strip().split()
    i = 0
    while i < len(tokens):
        token = tokens[i].upper()

        if token in ("FROM", "TO", "SUBJECT", "BODY", "SINCE", "BEFORE"):
            if i + 1 >= len(tokens):
                break
            i += 1
            value = tokens[i]
            if value and value[0] in ('"', "'"):
                quote = value[0]
                if value.endswith(quote) and len(value) > 1:
                    value = value[1:-1]
                else:
                    collected = [value[1:]]
                    while i + 1 < len(tokens):
                        i += 1
                        nxt = tokens[i]
                        if nxt.endswith(quote):
                            collected.append(nxt[:-1])
                            break
                        collected.append(nxt)
                    value = " ".join(collected)
            criteria.append(f'{token} "{value}"')

        elif token in ("UNREAD", "SEEN", "FLAGGED", "UNANSWERED", "DELETED", "DRAFT", "ALL"):
            criteria.append(token)

        i += 1

    return criteria if criteria else ["ALL"]


def _get_imap_connection() -> imaplib.IMAP4:
    """Create and return authenticated IMAP connection."""
    (
        EMAIL_DEFAULT_FOLDER,
        EMAIL_FETCH_BODY,
        EMAIL_IMAP_HOST,
        EMAIL_IMAP_PORT,
        EMAIL_IMAP_SSL,
        EMAIL_MAX_RESULTS,
        EMAIL_PASSWORD,
        EMAIL_USERNAME,
    ) = _get_config()
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        raise EmailAuthError("Email credentials not configured. Set EMAIL_USERNAME and EMAIL_PASSWORD in .env")

    try:
        if EMAIL_IMAP_SSL:
            conn = imaplib.IMAP4_SSL(EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, timeout=30)
        else:
            conn = imaplib.IMAP4(EMAIL_IMAP_HOST, EMAIL_IMAP_PORT, timeout=30)
            conn.starttls()
    except Exception as e:
        raise EmailConnectionError(f"Failed to connect to {EMAIL_IMAP_HOST}:{EMAIL_IMAP_PORT}: {e}")

    try:
        conn.login(EMAIL_USERNAME, EMAIL_PASSWORD)
    except imaplib.IMAP4.error as e:
        conn.logout()
        raise EmailAuthError(f"Authentication failed: {e}")

    return conn


def list_folders() -> List[str]:
    """List all available mailbox folders."""
    try:
        conn = _get_imap_connection()
        try:
            typ, data = conn.list()
            if typ != "OK":
                raise EmailError("Failed to list folders")
            folders = []
            for line in data:
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                # Parse: '(\\HasNoChildren) "/" "INBOX"'
                match = re.search(r'"([^"]+)"\s*$', line)
                if match:
                    folders.append(match.group(1))
            return folders
        finally:
            conn.logout()
    except (EmailAuthError, EmailConnectionError):
        raise
    except Exception as e:
        logger.error(f"Error listing folders: {e}")
        raise EmailError(f"Failed to list folders: {e}")


def check_email(folder: Optional[str] = None, max_results: Optional[int] = None, unread_only: bool = False) -> str:
    """List recent emails in a folder.

    Args:
        folder: Mailbox folder (default from config EMAIL_DEFAULT_FOLDER)
        max_results: Maximum number of emails to return
        unread_only: Only show unread emails

    Returns:
        Formatted string with From, Subject, Date, flags for each email
    """
    folder = folder or _get_default_folder()
    if max_results is None:
        max_results = _get_max_results()

    try:
        conn = _get_imap_connection()
        try:
            typ, data = conn.select(folder, readonly=True)
            if typ != "OK":
                raise EmailFolderError(f"Folder not found: {folder}")

            typ, data = conn.search(None, "UNSEEN" if unread_only else "ALL")
            if typ != "OK":
                raise EmailError("Search failed")

            uids = data[0].split()
            if not uids:
                return f"No {'unread ' if unread_only else ''}emails in {folder}."

            # Get most recent first (UIDs are ascending, so take last max_results)
            recent_uids = uids[-max_results:][::-1]

            lines = [f"Emails in {folder} ({'unread ' if unread_only else ''}{len(recent_uids)} shown):"]

            for uid in recent_uids:
                typ, msg_data = conn.fetch(uid, "(FLAGS ENVELOPE)")
                if typ != "OK":
                    continue

                # Parse envelope and flags
                flags = ""
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        _, data = response_part
                        if isinstance(data, bytes):
                            # Parse the fetch response
                            # Format: b'1 (FLAGS (\\Seen) ENVELOPE ("date" "subject" ...))'
                            data_str = data.decode("utf-8", errors="replace")
                            # Extract flags
                            flags_match = re.search(r"FLAGS\s*\(([^)]*)\)", data_str)
                            if flags_match:
                                flags = flags_match.group(1).replace("\\", "")
                            # Extract envelope - simplified parsing
                            # In practice, we'll fetch more details in read_email
                            pass

                # Fetch headers for display
                typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE)])")
                if typ != "OK":
                    lines.append(f"  [{uid}] (could not fetch headers)")
                    continue

                from_addr = ""
                subject = ""
                date_str = ""

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        _, header_data = response_part
                        if header_data:
                            msg = email.message_from_bytes(header_data)
                            from_addr = _format_email_address(msg.get("From", ""))
                            subject = _decode_header(msg.get("Subject", ""))
                            date_str = msg.get("Date", "")

                flags_display = f" [{flags}]" if flags else ""
                lines.append(f"  [{uid}] From: {from_addr} | Subject: {subject[:80]} | Date: {date_str}{flags_display}")

            return "\n".join(lines)
        finally:
            conn.logout()
    except (EmailAuthError, EmailConnectionError, EmailFolderError):
        raise
    except Exception as e:
        logger.error(f"Error checking email: {e}")
        raise EmailError(f"Failed to check email: {e}")


def read_email(message_id: str, folder: Optional[str] = None, include_body: bool = True) -> str:
    """Read full email by message ID (UID).

    Args:
        message_id: Email UID from check_email
        folder: Mailbox folder (default from config)
        include_body: Include full body text

    Returns:
        Formatted string with all headers and body
    """
    folder = folder or _get_default_folder()

    try:
        conn = _get_imap_connection()
        try:
            typ, data = conn.select(folder, readonly=True)
            if typ != "OK":
                raise EmailFolderError(f"Folder not found: {folder}")

            typ, data = conn.fetch(message_id, "(BODY.PEEK[])")
            if typ != "OK":
                raise EmailMessageError(f"Message not found: {message_id}")

            # Parse full message
            raw_email = None
            for response_part in data:
                if isinstance(response_part, tuple):
                    _, msg_data = response_part
                    if msg_data:
                        raw_email = msg_data
                        break

            if not raw_email:
                raise EmailMessageError(f"Message not found: {message_id}")

            msg = email.message_from_bytes(raw_email)

            # Extract headers
            from_addr = _format_email_address(msg.get("From", ""))
            to_addr = _format_email_address(msg.get("To", ""))
            cc_addr = _format_email_address(msg.get("Cc", ""))
            subject = _decode_header(msg.get("Subject", ""))
            date_str = msg.get("Date", "")
            message_id_hdr = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")

            # Extract body
            text_body, html_body = _get_body_from_message(msg)

            lines = [
                f"Message-ID: {message_id}",
                f"From: {from_addr}",
                f"To: {to_addr}",
            ]
            if cc_addr:
                lines.append(f"Cc: {cc_addr}")
            lines.append(f"Subject: {subject}")
            lines.append(f"Date: {date_str}")
            if message_id_hdr:
                lines.append(f"Message-ID: {message_id_hdr}")
            if in_reply_to:
                lines.append(f"In-Reply-To: {in_reply_to}")
            if references:
                lines.append(f"References: {references}")
            lines.append("")  # blank line

            if include_body:
                if text_body:
                    lines.append("--- Text Body ---")
                    lines.append(text_body)
                    lines.append("")
                if html_body and not text_body:  # Only show HTML if no text
                    lines.append("--- HTML Body ---")
                    lines.append(html_body[:2000] + ("..." if len(html_body) > 2000 else ""))
                    lines.append("")

            return "\n".join(lines)
        finally:
            conn.logout()
    except (EmailAuthError, EmailConnectionError, EmailFolderError, EmailMessageError):
        raise
    except Exception as e:
        logger.error(f"Error reading email: {e}")
        raise EmailError(f"Failed to read email: {e}")


def search_email(query: str, folder: Optional[str] = None, max_results: Optional[int] = None) -> str:
    """Search emails with IMAP criteria.

    Args:
        query: IMAP search criteria (e.g., 'FROM "boss" SUBJECT "report" UNREAD')
        folder: Mailbox folder (default from config)
        max_results: Maximum results to return

    Returns:
        Formatted list of matching emails
    """
    folder = folder or _get_default_folder()
    if max_results is None:
        max_results = _get_max_results()
    criteria = _build_search_criteria(query)

    try:
        conn = _get_imap_connection()
        try:
            typ, data = conn.select(folder, readonly=True)
            if typ != "OK":
                raise EmailFolderError(f"Folder not found: {folder}")

            typ, data = conn.search(None, *criteria)
            if typ != "OK":
                raise EmailError("Search failed")

            uids = data[0].split()
            if not uids:
                return f"No emails matching: {query}"

            # Get most recent first
            recent_uids = uids[-max_results:][::-1]

            lines = [f"Search results for: {query} ({len(recent_uids)} shown):"]

            for uid in recent_uids:
                typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE)])")
                if typ != "OK":
                    continue

                from_addr = ""
                to_addr = ""
                cc_addr = ""
                subject = ""
                date_str = ""

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        _, header_data = response_part
                        if header_data:
                            msg = email.message_from_bytes(header_data)
                            from_addr = _format_email_address(msg.get("From", ""))
                            to_addr = _format_email_address(msg.get("To", ""))
                            cc_addr = _format_email_address(msg.get("Cc", ""))
                            subject = _decode_header(msg.get("Subject", ""))
                            date_str = msg.get("Date", "")

                parts = [f"  [{uid}] From: {from_addr}"]
                if to_addr:
                    parts.append(f"To: {to_addr}")
                if cc_addr:
                    parts.append(f"Cc: {cc_addr}")
                parts.append(f"Subject: {subject[:80]}")
                parts.append(f"Date: {date_str}")
                lines.append(" | ".join(parts))

            return "\n".join(lines)
        finally:
            conn.logout()
    except (EmailAuthError, EmailConnectionError, EmailFolderError):
        raise
    except Exception as e:
        logger.error(f"Error searching email: {e}")
        raise EmailError(f"Failed to search email: {e}")


def get_email_summary(folder: Optional[str] = None, days: int = 7) -> str:
    """Get summary of email folder: total, unread, top senders, date range."""
    folder = folder or _get_default_folder()

    try:
        conn = _get_imap_connection()
        try:
            typ, data = conn.select(folder, readonly=True)
            if typ != "OK":
                raise EmailFolderError(f"Folder not found: {folder}")

            # Total messages
            typ, data = conn.search(None, "ALL")
            total = len(data[0].split()) if data[0] else 0

            # Unread messages
            typ, data = conn.search(None, "UNSEEN")
            unread = len(data[0].split()) if data[0] else 0

            # Recent messages (last N days)
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            typ, data = conn.search(None, f"SINCE {since_date}")
            recent = len(data[0].split()) if data[0] else 0

            # Top senders (fetch recent messages and count from addresses)
            typ, data = conn.search(None, f"SINCE {since_date}")
            uids = data[0].split() if data[0] else []
            sender_counts = {}

            for uid in uids[-50:]:  # Sample last 50
                typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
                if typ == "OK":
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            _, header_data = response_part
                            if header_data:
                                msg = email.message_from_bytes(header_data)
                                from_addr = _format_email_address(msg.get("From", ""))
                                if from_addr:
                                    sender_counts[from_addr] = sender_counts.get(from_addr, 0) + 1

            top_senders = sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            lines = [
                f"Email Summary for {folder} (last {days} days):",
                f"  Total messages: {total}",
                f"  Unread: {unread}",
                f"  Recent ({days} days): {recent}",
            ]

            if top_senders:
                lines.append("  Top senders:")
                for sender, count in top_senders:
                    lines.append(f"    {sender}: {count}")

            return "\n".join(lines)
        finally:
            conn.logout()
    except (EmailAuthError, EmailConnectionError, EmailFolderError):
        raise
    except Exception as e:
        logger.error(f"Error getting email summary: {e}")
        raise EmailError(f"Failed to get email summary: {e}")


# Tool registry and definitions for brain.py integration
EMAIL_TOOLS = {
    "check_email": check_email,
    "read_email": read_email,
    "search_email": search_email,
    "list_email_folders": list_folders,
    "get_email_summary": get_email_summary,
}

EMAIL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_email",
            "description": "List recent emails in a folder (default INBOX). Returns From, Subject, Date, flags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Mailbox folder (default INBOX)"},
                    "max_results": {"type": "integer", "description": "Max emails to return (default 20)"},
                    "unread_only": {"type": "boolean", "description": "Only show unread emails", "default": False},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read full email by message ID (UID). Returns headers + body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Email UID from check_email"},
                    "folder": {"type": "string", "description": "Mailbox folder (default INBOX)"},
                    "include_body": {
                        "type": "boolean",
                        "description": "Include full body text (default true)",
                        "default": True,
                    },
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_email",
            "description": (
                "Search emails with IMAP criteria. "
                "Examples: 'FROM \"boss\" SUBJECT \"report\"', 'UNREAD SINCE 01-Jan-2025'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "IMAP search criteria"},
                    "folder": {"type": "string", "description": "Mailbox folder (default INBOX)"},
                    "max_results": {"type": "integer", "description": "Max results (default 20)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_email_folders",
            "description": "List all available mailbox folders",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_email_summary",
            "description": "Get summary: total, unread, top senders, date range",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string", "description": "Mailbox folder (default INBOX)"},
                    "days": {"type": "integer", "description": "Look back N days (default 7)", "default": 7},
                },
                "required": [],
            },
        },
    },
]

# Export for tools/__init__.py
EMAIL_TOOLS_DICT = {
    "check_email": check_email,
    "read_email": read_email,
    "search_email": search_email,
    "list_email_folders": list_folders,
    "get_email_summary": get_email_summary,
}

EMAIL_DEFINITIONS_LIST = EMAIL_DEFINITIONS
