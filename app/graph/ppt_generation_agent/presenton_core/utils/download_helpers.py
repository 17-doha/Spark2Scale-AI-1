import asyncio
import ipaddress
import os
import mimetypes
import socket
from typing import List, Optional
from urllib.parse import urlparse
import aiohttp
import uuid


def _is_private_ip(hostname: str) -> bool:
    """Return True if hostname resolves to a private/reserved IP address."""
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or str(ip) == "169.254.169.254"  # cloud metadata (AWS/Azure/GCP)
        )
    except Exception:
        return True  # fail closed — treat unresolvable as unsafe


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL has no hostname.")
    if _is_private_ip(hostname):
        raise ValueError(f"Requests to private/internal addresses are not allowed.")


async def download_file(
    url: str, save_directory: str, headers: Optional[dict] = None
) -> Optional[str]:
    try:
        _validate_url(url)
    except ValueError as e:
        print(f"Blocked download of {url}: {e}")
        return None

    try:
        os.makedirs(save_directory, exist_ok=True)

        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)

        if not filename or "." not in filename:
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.head(url, headers=headers, allow_redirects=False) as response:
                    if response.status == 200:
                        content_disposition = response.headers.get("Content-Disposition", "")
                        if "filename=" in content_disposition:
                            filename = content_disposition.split("filename=")[1].strip("\"'")
                        else:
                            content_type = response.headers.get("Content-Type", "")
                            if content_type:
                                extension = mimetypes.guess_extension(content_type.split(";")[0])
                                if extension:
                                    filename = f"{uuid.uuid4()}{extension}"

        # Always use a random safe filename to prevent path traversal
        ext = os.path.splitext(filename)[1] if filename and "." in filename else ""
        safe_filename = f"{uuid.uuid4()}{ext}"
        save_path = os.path.join(save_directory, safe_filename)

        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(url, headers=headers, allow_redirects=False) as response:
                if response.status == 200:
                    with open(save_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(8192):
                            file.write(chunk)
                    print(f"File downloaded successfully: {save_path}")
                    return save_path
                else:
                    print(f"Failed to download file. HTTP status: {response.status}")
                    return None

    except Exception as e:
        print(f"Error downloading file from {url}: {e}")
        return None


async def download_files(
    urls: List[str], save_directory: str, headers: Optional[dict] = None
) -> List[Optional[str]]:
    print(f"Starting download of {len(urls)} files to {save_directory}")
    coroutines = [download_file(url, save_directory, headers) for url in urls]
    results = await asyncio.gather(*coroutines, return_exceptions=True)
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Exception during download of {urls[i]}: {result}")
            final_results.append(None)
        else:
            final_results.append(result)

    successful_downloads = sum(1 for result in final_results if result is not None)
    print(f"Download completed: {successful_downloads}/{len(urls)} files downloaded successfully")
    return final_results
