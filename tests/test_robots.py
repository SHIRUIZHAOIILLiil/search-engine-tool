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

    def test_crawl_delay_returns_none_when_not_set(self):
        robots_txt = (
            "User-agent: *\n"
            "Disallow: /private/\n"
        )
        policy = RobotsPolicy.from_text(robots_txt, "TestBot")

        self.assertIsNone(policy.crawl_delay())


if __name__ == "__main__":
    unittest.main()
