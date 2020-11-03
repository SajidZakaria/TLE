import functools
import time
import traceback
import aiohttp
import bs4

from discord.ext import commands

from tle import constants
from tle.util import codeforces_common as cf_common


def timed_command(coro):
    @functools.wraps(coro)
    async def wrapper(cog, ctx, *args):
        await ctx.send('Running...')
        begin = time.time()
        await coro(cog, ctx, *args)
        elapsed = time.time() - begin
        await ctx.send(f'Completed in {elapsed:.2f} seconds')

    return wrapper


class CacheControl(commands.Cog):
    """Cog to manually trigger update of cached data. Intended for dev/admin use."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(brief='Commands to force reload of cache',
                    invoke_without_command=True)
    @commands.has_role(constants.TLE_ADMIN)
    async def cache(self, ctx):
        await ctx.send_help('cache')

    @cache.command()
    @commands.has_role(constants.TLE_ADMIN)
    @timed_command
    async def contests(self, ctx):
        await cf_common.cache2.contest_cache.reload_now()

    @cache.command()
    @commands.has_role(constants.TLE_ADMIN)
    @timed_command
    async def problems(self, ctx):
        await cf_common.cache2.problem_cache.reload_now()

    @cache.command(usage='[missing|all|contest_id]')
    @commands.has_role(constants.TLE_ADMIN)
    @timed_command
    async def ratingchanges(self, ctx, contest_id='missing'):
        """Defaults to 'missing'. Mode 'all' clears existing cached changes.
        Mode 'contest_id' clears existing changes with the given contest id.
        """
        if contest_id not in ('all', 'missing'):
            try:
                contest_id = int(contest_id)
            except ValueError:
                return
        if contest_id == 'all':
            await ctx.send('This will take a while')
            count = await cf_common.cache2.rating_changes_cache.fetch_all_contests()
        elif contest_id == 'missing':
            await ctx.send('This may take a while')
            count = await cf_common.cache2.rating_changes_cache.fetch_missing_contests()
        else:
            count = await cf_common.cache2.rating_changes_cache.fetch_contest(contest_id)
        await ctx.send(f'Done, fetched {count} changes and recached handle ratings')

    @cache.command(usage='contest_id|all')
    @commands.has_role(constants.TLE_ADMIN)
    @timed_command
    async def problemsets(self, ctx, contest_id):
        """Mode 'all' clears all existing cached problems. Mode 'contest_id'
        clears existing problems with the given contest id.
        """
        if contest_id == 'all':
            await ctx.send('This will take a while')
            count = await cf_common.cache2.problemset_cache.update_for_all()
        else:
            try:
                contest_id = int(contest_id)
            except ValueError:
                return
            count = await cf_common.cache2.problemset_cache.update_for_contest(contest_id)
        await ctx.send(f'Done, fetched {count} problems')

    @cache.command(usage='list_key name')
    @commands.has_role('Admin')
    @timed_command
    async def list(self, ctx, list_key, name):
        session = aiohttp.ClientSession()

        async def __single_query(url):
            nonlocal session
            async with session.get(url) as resp:
                html_raw = await resp.text()
                soup = bs4.BeautifulSoup(html_raw, features="lxml")
                table = soup.find_all("table")[0]
                rows = table.find_all("tr")[1:]
                result = []
                for row in rows:
                    span = row.find("span", {"class": "small"})
                    if span is None:
                        continue
                    cnt = int(span.text.split('/')[0])
                    col = row.find_all("td")[0]
                    problem_id = col.text.strip()
                    result.append([problem_id, cnt])
            return result

        await ctx.send('This will take a while')
        page_num = 0
        async with session.get("https://codeforces.com/problemset/") as resp:
            html_raw = await resp.text()
            soup = bs4.BeautifulSoup(html_raw, features="lxml")
            page_div = soup.find_all("ul")[-1]
            page_num = page_div.find_all("span", {"class": "page-index"})[-1].text
            page_num = int(page_num)

        await ctx.send(f"{page_num} pages to check...")
        url = "https://codeforces.com/problemset/page/{}?list={}"
        counts = []
        for i in range(1, page_num + 1):
            current_page = url.format(i, list_key)
            print(url.format(i, list_key))
            result = await __single_query(current_page)
            if result is None:
                break
            counts += result

        await ctx.send(f'Found result for {len(counts)} problems')
        result = "\n".join(f"{item[0]},{item[1]}" for item in counts)
        with open(f"data/list/{name}.csv", "w") as file:
            file.write(result)
        await session.close()

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            error = error.__cause__
        lines = traceback.format_exception(type(error), error, error.__traceback__)
        msg = '\n'.join(lines)
        discord_msg_char_limit = 2000
        char_limit = discord_msg_char_limit - 2 * len('```')
        too_long = len(msg) > char_limit
        msg = msg[:char_limit]
        await ctx.send(f'```{msg}```')
        if too_long:
            await ctx.send('Check logs for full stack trace')


def setup(bot):
    bot.add_cog(CacheControl(bot))
