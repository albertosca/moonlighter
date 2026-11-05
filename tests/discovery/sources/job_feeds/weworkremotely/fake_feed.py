"""A We Work Remotely RSS feed and the fake client that serves it."""

from unittest.mock import AsyncMock, MagicMock

WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>Acme: Senior Backend Engineer</title>
      <region>Anywhere in the World</region>
      <description>&lt;p&gt;Build &lt;strong&gt;things&lt;/strong&gt;.&lt;/p&gt;</description>
      <pubDate>Tue, 30 Jun 2026 20:32:52 +0000</pubDate>
      <link>https://weworkremotely.com/remote-jobs/acme-senior-backend-engineer</link>
    </item>
    <item>
      <title>Frontend Developer Wanted</title>
      <region>USA Only</region>
      <description>No colon in title, no company prefix.</description>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
      <link>https://weworkremotely.com/remote-jobs/frontend-developer-wanted</link>
    </item>
    <item>
      <title>Missing Link Co: Some Role</title>
      <region>Worldwide</region>
      <description>No link element -- must be skipped.</description>
      <pubDate>Wed, 01 Jul 2026 10:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


def make_rss_client(body, status=200):
    async def fake_get(url, headers=None):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.text = body
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=fake_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client
