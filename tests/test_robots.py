import unittest

from src.robots import RobotsPolicy


class RobotsPolicyTests(unittest.TestCase):
    def test_permissive_allows_every_url(self):
        policy = RobotsPolicy.permissive()

        self.assertTrue(policy.is_allowed("https://example.com/"))
        self.assertTrue(policy.is_allowed("https://example.com/anything/at/all"))

    def test_permissive_declares_no_crawl_delay(self):
        policy = RobotsPolicy.permissive()

        self.assertIsNone(policy.crawl_delay())

    def test_from_text_disallows_path(self):
        robots_txt = (
            "User-agent: *\n"
            "Disallow: /private/\n"
        )
        policy = RobotsPolicy.from_text(robots_txt, "TestBot")

        self.assertFalse(policy.is_allowed("https://example.com/private/secret"))
        self.assertTrue(policy.is_allowed("https://example.com/public/"))

    def test_from_text_returns_crawl_delay(self):
        robots_txt = (
            "User-agent: *\n"
            "Crawl-delay: 10\n"
        )
        policy = RobotsPolicy.from_text(robots_txt, "TestBot")

        self.assertEqual(policy.crawl_delay(), 10.0)

    def test_from_text_user_agent_specific_rules_block_target_bot(self):
        robots_txt = (
            "User-agent: BadBot\n"
            "Disallow: /\n"
            "\n"
            "User-agent: *\n"
            "Disallow:\n"
        )

        bad = RobotsPolicy.from_text(robots_txt, "BadBot")
        good = RobotsPolicy.from_text(robots_txt, "GoodBot")

        self.assertFalse(bad.is_allowed("https://example.com/anything"))
        self.assertTrue(good.is_allowed("https://example.com/anything"))

    def test_from_url_fetches_and_parses_robots_txt(self):
        captured: list[str] = []

        def fake_fetch(url: str) -> str:
            captured.append(url)
            return "User-agent: *\nDisallow: /private/\n"

        policy = RobotsPolicy.from_url(
            "https://example.com/some/page/",
            "TestBot",
            fetch=fake_fetch,
        )

        self.assertEqual(captured, ["https://example.com/robots.txt"])
        self.assertFalse(policy.is_allowed("https://example.com/private/x"))
        self.assertTrue(policy.is_allowed("https://example.com/public/"))

    def test_from_url_falls_back_to_permissive_on_fetch_error(self):
        def failing_fetch(url: str) -> str:
            raise RuntimeError("network down")

        policy = RobotsPolicy.from_url(
            "https://example.com/",
            "TestBot",
            fetch=failing_fetch,
        )

        self.assertTrue(policy.is_allowed("https://example.com/anything"))
        self.assertIsNone(policy.crawl_delay())

    def test_from_url_always_targets_host_root(self):
        captured: list[str] = []

        def fake_fetch(url: str) -> str:
            captured.append(url)
            return ""

        RobotsPolicy.from_url(
            "https://example.com/deep/nested/path/",
            "TestBot",
            fetch=fake_fetch,
        )

        self.assertEqual(captured, ["https://example.com/robots.txt"])

    def test_crawl_delay_returns_none_when_not_set(self):
        robots_txt = (
            "User-agent: *\n"
            "Disallow: /private/\n"
        )
        policy = RobotsPolicy.from_text(robots_txt, "TestBot")

        self.assertIsNone(policy.crawl_delay())


if __name__ == "__main__":
    unittest.main()
