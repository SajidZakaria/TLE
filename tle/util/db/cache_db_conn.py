import json
import psycopg2

from tle.util import codeforces_api as cf

class CacheDbConn:
    def __init__(self, db_url):
        self.conn = psycopg2.connect(db_url)
        self.create_tables()

    def create_tables(self):
        # Table for contests from the contest.list endpoint.
        cur = self.conn.cursor()
        cur.execute(
            'CREATE TABLE IF NOT EXISTS contest ('
            'id             INTEGER NOT NULL,'
            'name           TEXT,'
            'start_time     INTEGER,'
            'duration       INTEGER,'
            'type           TEXT,'
            'phase          TEXT,'
            'prepared_by    TEXT,'
            'PRIMARY KEY (id)'
            ')'
        )

        # Table for problems from the problemset.problems endpoint.
        cur.execute(
            'CREATE TABLE IF NOT EXISTS problem ('
            'contest_id       INTEGER,'
            'problemset_name  TEXT,'
            '[index]          TEXT,'
            'name             TEXT NOT NULL,'
            'type             TEXT,'
            'points           REAL,'
            'rating           INTEGER,'
            'tags             TEXT,'
            'PRIMARY KEY (name)'
            ')'
        )

        # Table for rating changes fetched from contest.ratingChanges endpoint for every contest.
        cur.execute(
            'CREATE TABLE IF NOT EXISTS rating_change ('
            'contest_id           INTEGER NOT NULL,'
            'handle               TEXT NOT NULL,'
            'rank                 INTEGER,'
            'rating_update_time   INTEGER,'
            'old_rating           INTEGER,'
            'new_rating           INTEGER,'
            'UNIQUE (contest_id, handle)'
            ')'
        )
        cur.execute('CREATE INDEX IF NOT EXISTS ix_rating_change_contest_id '
                          'ON rating_change (contest_id)')
        cur.execute('CREATE INDEX IF NOT EXISTS ix_rating_change_handle '
                          'ON rating_change (handle)')

        # Table for problems fetched from contest.standings endpoint for every contest.
        # This is separate from table problem as it contains the same problem twice if it
        # appeared in both Div 1 and Div 2 of some round.
        cur.execute(
            'CREATE TABLE IF NOT EXISTS problem2 ('
            'contest_id       INTEGER,'
            'problemset_name  TEXT,'
            '[index]          TEXT,'
            'name             TEXT NOT NULL,'
            'type             TEXT,'
            'points           REAL,'
            'rating           INTEGER,'
            'tags             TEXT,'
            'PRIMARY KEY (contest_id, [index])'
            ')'
        )
        cur.execute('CREATE INDEX IF NOT EXISTS ix_problem2_contest_id '
                          'ON problem2 (contest_id)')

        self.conn.commit()

    def cache_contests(self, contests):
        query = ('INSERT INTO contest '
                 '(id, name, start_time, duration, type, phase, prepared_by) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s) '
                 'ON CONFLICT ON CONSTRAINT (id) '
                 'DO UPDATE SET '
                 'name = EXCLUDED.name,'
                 'start_time = EXCLUDED.start_time,'
                 'duration = EXCLUDED.duration,'
                 'type = EXCLUDED.type,'
                 'phase = EXCLUDED.phase,'
                 'prepared_by = EXCLUDED.prepared_by;')
        cur = self.conn.cursor()
        rc = cur.executemany(query, contests).rowcount
        self.conn.commit()
        return rc

    def fetch_contests(self):
        query = ('SELECT id, name, start_time, duration, type, phase, prepared_by '
                 'FROM contest')
        cur = self.conn.cursor()
        res = cur.execute(query).fetchall()
        return [cf.Contest._make(contest) for contest in res]

    @staticmethod
    def _squish_tags(problem):
        return (problem.contestId, problem.problemsetName, problem.index, problem.name,
                problem.type, problem.points, problem.rating, json.dumps(problem.tags))

    def cache_problems(self, problems):
        query = ('INSERT INTO problem '
                 '(contest_id, problemset_name, [index], name, type, points, rating, tags) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
                 'ON CONFLICT ON CONSTRAINT (contest_id) '
                 'DO UPDATE SET '
                 'problemset_name = EXCLUDED.problemset_name,'
                 '[index] = EXCLUDED.[index],'
                 'name = EXCLUDED.name,'
                 'type = EXCLUDED.type,'
                 'points = EXCLUDED.points,'
                 'rating = EXCLUDED.rating,'
                 'tags = EXCLUDED.tags;')
        cur = self.conn.cursor()
        rc = cur.executemany(query, list(map(self._squish_tags, problems))).rowcount
        self.conn.commit()
        return rc

    @staticmethod
    def _unsquish_tags(problem):
        args, tags = problem[:-1], json.loads(problem[-1])
        return cf.Problem(*args, tags)

    def fetch_problems(self):
        query = ('SELECT contest_id, problemset_name, [index], name, type, points, rating, tags '
                 'FROM problem')
        cur = self.conn.cursor()
        res = cur.execute(query).fetchall()
        return list(map(self._unsquish_tags, res))

    def save_rating_changes(self, changes):
        change_tuples = [(change.contestId,
                          change.handle,
                          change.rank,
                          change.ratingUpdateTimeSeconds,
                          change.oldRating,
                          change.newRating) for change in changes]
        query = ('INSERT INTO rating_change '
                 '(contest_id, handle, rank, rating_update_time, old_rating, new_rating) '
                 'VALUES (%s, %s, %s, %s, %s, %s) '
                 'ON CONFLICT ON CONSTRAINT (contest_id) '
                 'DO UPDATE SET '
                 'handle = EXCLUDED.handle,'
                 'rank = EXCLUDED.rank,'
                 'rating_update_time = EXCLUDED.rating_update_time,'
                 'old_rating = EXCLUDED.old_rating,'
                 'new_rating = EXCLUDED.new_rating;')
        cur = self.conn.cursor()
        rc = cur.executemany(query, change_tuples).rowcount
        self.conn.commit()
        return rc

    def clear_rating_changes(self, contest_id=None):
        cur = self.conn.cursor()
        if contest_id is None:
            query = 'DELETE FROM rating_change'
            cur.execute(query)
        else:
            query = 'DELETE FROM rating_change WHERE contest_id = %s'
            cur.execute(query, (contest_id,))
        self.conn.commit()

    def get_users_with_more_than_n_contests(self, time_cutoff, n):
        query = ('SELECT handle, COUNT(*) AS num_contests '
                 'FROM rating_change GROUP BY handle HAVING num_contests >= %s '
                 'AND MAX(rating_update_time) >= %s')
        cur = self.conn.cursor()
        res = cur.execute(query, (n, time_cutoff,)).fetchall()
        return [user[0] for user in res]

    def get_all_rating_changes(self):
        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'ORDER BY rating_update_time')
        cur = self.conn.cursor()
        res = cur.execute(query)
        return (cf.RatingChange._make(change) for change in res)

    def get_rating_changes_for_contest(self, contest_id):
        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'WHERE r.contest_id = %s')
        cur = self.conn.cursor()
        res = cur.execute(query, (contest_id,)).fetchall()
        return [cf.RatingChange._make(change) for change in res]

    def has_rating_changes_saved(self, contest_id):
        query = ('SELECT contest_id '
                 'FROM rating_change '
                 'WHERE contest_id = %s')
        cur = self.conn.cursor()
        res = cur.execute(query, (contest_id,)).fetchone()
        return res is not None

    def get_rating_changes_for_handle(self, handle):
        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'WHERE r.handle = %s')
        cur = self.conn.cursor()
        res = cur.execute(query, (handle,)).fetchall()
        return [cf.RatingChange._make(change) for change in res]

    def cache_problemset(self, problemset):
        query = ('INSERT INTO problem2 '
                 '(contest_id, problemset_name, [index], name, type, points, rating, tags) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
                 'ON CONFLICT ON CONSTRAINT (contest_id) '
                 'DO UPDATE SET '
                 'problemset_name = EXCLUDED.problemset_name,'
                 '[index] = EXCLUDED.[index],'
                 'name = EXCLUDED.name,'
                 'type = EXCLUDED.type,'
                 'points = EXCLUDED.points,'
                 'rating = EXCLUDED.rating,'
                 'tags = EXCLUDED.tags;')
        cur = self.conn.cursor()
        rc = cur.executemany(query, list(map(self._squish_tags, problemset))).rowcount
        self.conn.commit()
        return rc

    def fetch_problems2(self):
        query = ('SELECT contest_id, problemset_name, [index], name, type, points, rating, tags '
                 'FROM problem2 ')
        cur = self.conn.cursor()
        res = cur.execute(query).fetchall()
        return list(map(self._unsquish_tags, res))

    def clear_problemset(self, contest_id=None):
        cur = self.conn.cursor()
        if contest_id is None:
            query = 'DELETE FROM problem2'
            cur.execute(query)
        else:
            query = 'DELETE FROM problem2 WHERE contest_id = %s'
            cur.execute(query, (contest_id,))

    def fetch_problemset(self, contest_id):
        query = ('SELECT contest_id, problemset_name, [index], name, type, points, rating, tags '
                 'FROM problem2 '
                 'WHERE contest_id = %s')
        cur = self.conn.cursor()
        res = cur.execute(query, (contest_id,)).fetchall()
        return list(map(self._unsquish_tags, res))

    def problemset_empty(self):
        query = 'SELECT 1 FROM problem2'
        cur = self.conn.cursor()
        res = cur.execute(query).fetchone()
        return res is None

    def close(self):
        self.conn.close()
