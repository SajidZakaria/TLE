import json
import psycopg2
import psycopg2.extras

from tle.util import codeforces_api as cf


class CacheDbConn:
    def __init__(self, db_file):
        self.connection = psycopg2.connect(db_file)
        self.conn = None

        self.create_tables()

    def create_tables(self):
        self.conn = self.connection.cursor()
        # Table for contests from the contest.list endpoint.
        self.conn.execute(
            'CREATE TABLE IF NOT EXISTS contest ('
            'id             INTEGER NOT NULL,'
            'name           TEXT,'
            'start_time     INTEGER,'
            'duration       INTEGER,'
            'type           TEXT,'
            'phase          TEXT,'
            'prepared_by    TEXT,'
            'PRIMARY KEY (id)'
            ');'
        )

        # Table for problems from the problemset.problems endpoint.
        self.conn.execute(
            'CREATE TABLE IF NOT EXISTS problem ('
            'contest_id       INTEGER,'
            'problemset_name  TEXT,'
            'txtIndex         TEXT,'
            'name             TEXT NOT NULL,'
            'type             TEXT,'
            'points           REAL,'
            'rating           INTEGER,'
            'tags             TEXT,'
            'PRIMARY KEY (name)'
            ');'
        )

        # Table for rating changes fetched from contest.ratingChanges endpoint for every contest.
        self.conn.execute(
            'CREATE TABLE IF NOT EXISTS rating_change ('
            'contest_id           INTEGER NOT NULL,'
            'handle               TEXT NOT NULL,'
            'rank                 INTEGER,'
            'rating_update_time   INTEGER,'
            'old_rating           INTEGER,'
            'new_rating           INTEGER,'
            'UNIQUE (contest_id)'
            ');'
        )
        self.conn.execute('CREATE INDEX IF NOT EXISTS ix_rating_change_contest_id '
                          'ON rating_change (contest_id)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS ix_rating_change_handle '
                          'ON rating_change (handle)')

        # Table for problems fetched from contest.standings endpoint for every contest.
        # This is separate from table problem as it contains the same problem twice if it
        # appeared in both Div 1 and Div 2 of some round.
        self.conn.execute(
            'CREATE TABLE IF NOT EXISTS problem2 ('
            'contest_id       INTEGER,'
            'problemset_name  TEXT,'
            'txtIndex         TEXT,'
            'name             TEXT NOT NULL,'
            'type             TEXT,'
            'points           REAL,'
            'rating           INTEGER,'
            'tags             TEXT,'
            'PRIMARY KEY (contest_id, txtIndex)'
            ');'
        )
        self.conn.execute('CREATE INDEX IF NOT EXISTS ix_problem2_contest_id '
                          'ON problem2 (contest_id)')
        self.connection.commit()
        self.conn.close()

    def cache_contests(self, contests):
        self.conn = self.connection.cursor()
        query = '''
            INSERT INTO contest
                (id, name, start_time, duration, type, phase, prepared_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                id = EXCLUDED.id,
                name = EXCLUDED.name,
                start_time = EXCLUDED.start_time,
                duration = EXCLUDED.duration,
                type = EXCLUDED.type,
                phase = EXCLUDED.phase,
                prepared_by = EXCLUDED.prepared_by;
        '''

        self.conn.executemany(query, contests)
        rc = self.conn.rowcount

        self.connection.commit()
        self.conn.close()
        return rc

    def fetch_contests(self):
        self.conn = self.connection.cursor()
        query = ('SELECT id, name, start_time, duration, type, phase, prepared_by '
                 'FROM contest')
        self.conn.execute(query)
        res = self.conn.fetchall()
        self.conn.close()
        return [cf.Contest._make(contest) for contest in res]

    @staticmethod
    def _squish_tags(problem):
        return (problem.contestId, problem.problemsetName, problem.index, problem.name,
                problem.type, problem.points, problem.rating, json.dumps(problem.tags))

    def cache_problems(self, problems):
        self.conn = self.connection.cursor()
        query = '''
            INSERT INTO problem
                (contest_id, problemset_name, txtIndex, name, type, points, rating, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                contest_id = EXCLUDED.contest_id,
                problemset_name = EXCLUDED.problemset_name,
                txtIndex = EXCLUDED.txtIndex,
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                points = EXCLUDED.points,
                rating = EXCLUDED.rating,
                tags = EXCLUDED.tags;
        '''
        self.conn.executemany(query, list(map(self._squish_tags, problems)))
        rc = self.conn.rowcount
        self.connection.commit()
        self.conn.close()
        return rc

    @staticmethod
    def _unsquish_tags(problem):
        args, tags = problem[:-1], json.loads(problem[-1])
        return cf.Problem(*args, tags)

    def fetch_problems(self):
        self.conn = self.connection.cursor()
        query = ('SELECT contest_id, problemset_name, txtIndex, name, type, points, rating, tags '
                 'FROM problem')
        self.conn.execute(query)
        res = self.conn.fetchall()
        self.conn.close()
        return list(map(self._unsquish_tags, res))

    def save_rating_changes(self, changes):
        self.conn = self.connection.cursor()
        change_tuples = [(change.contestId,
                          change.handle,
                          change.rank,
                          change.ratingUpdateTimeSeconds,
                          change.oldRating,
                          change.newRating) for change in changes]
        query = '''
            INSERT INTO rating_change
                (contest_id, handle, rank, rating_update_time, old_rating, new_rating)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (contest_id) DO UPDATE SET
                contest_id = EXCLUDED.contest_id,
                handle = EXCLUDED.handle,
                rank = EXCLUDED.rank,
                rating_update_time = EXCLUDED.rating_update_time,
                old_rating = EXCLUDED.old_rating,
                new_rating = EXCLUDED.new_rating;
        '''

        self.conn.executemany(query, change_tuples)
        rc = self.conn.rowcount
        self.connection.commit()
        self.conn.close()
        return rc

    def clear_rating_changes(self, contest_id=None):
        self.conn = self.connection.cursor()

        if contest_id is None:
            query = 'DELETE FROM rating_change'
            self.conn.execute(query)
        else:
            query = 'DELETE FROM rating_change WHERE contest_id = %s'
            self.conn.execute(query, (contest_id,))
        self.connection.commit()
        self.conn.close()

    def get_users_with_more_than_n_contests(self, time_cutoff, n):
        self.conn = self.connection.cursor()

        query = ('SELECT handle, COUNT(*) AS num_contests '
                 'FROM rating_change GROUP BY handle HAVING num_contests >= %s '
                 'AND MAX(rating_update_time) >= %s')
        self.conn.execute(query, (n, time_cutoff,))
        res = self.conn.fetchall()
        self.conn.close()
        return [user[0] for user in res]

    def get_all_rating_changes(self):
        self.conn = self.connection.cursor()

        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'ORDER BY rating_update_time')
        self.conn.execute(query)
        res = self.conn.fetchall()
        self.conn.close()
        return (cf.RatingChange._make(change) for change in res)

    def get_rating_changes_for_contest(self, contest_id):
        self.conn = self.connection.cursor()

        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'WHERE r.contest_id = %s')
        self.conn.execute(query, (contest_id,))
        res = self.conn.fetchall()
        self.conn.close()
        return [cf.RatingChange._make(change) for change in res]

    def has_rating_changes_saved(self, contest_id):
        self.conn = self.connection.cursor()
        query = ('SELECT contest_id '
                 'FROM rating_change '
                 'WHERE contest_id = %s')
        self.conn.execute(query, (contest_id,))
        res = self.conn.fetchone()
        self.conn.close()
        return res is not None

    def get_rating_changes_for_handle(self, handle):
        self.conn = self.connection.cursor()

        query = ('SELECT contest_id, name, handle, rank, rating_update_time, old_rating, new_rating '
                 'FROM rating_change r '
                 'LEFT JOIN contest c '
                 'ON r.contest_id = c.id '
                 'WHERE r.handle = %s')
        self.conn.execute(query, (handle,))
        res = self.conn.fetchall()
        self.conn.close()
        return [cf.RatingChange._make(change) for change in res]

    def cache_problemset(self, problemset):
        self.conn = self.connection.cursor()

        query = '''
            INSERT INTO problem2
                (contest_id, problemset_name, txtIndex, name, type, points, rating, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (contest_id, txtIndex) DO UPDATE SET
                contest_id = EXCLUDED.contest_id,
                problemset_name = EXCLUDED.problemset_name,
                txtIndex = EXCLUDED.txtIndex,
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                points = EXCLUDED.points,
                rating = EXCLUDED.rating,
                tags = EXCLUDED.tags;
        '''

        self.conn.executemany(query, list(map(self._squish_tags, problemset)))
        rc = self.conn.rowcount
        self.connection.commit()
        self.conn.close()
        return rc

    def fetch_problems2(self):
        self.conn = self.connection.cursor()

        query = ('SELECT contest_id, problemset_name, txtIndex, name, type, points, rating, tags '
                 'FROM problem2 ')
        self.conn.execute(query)
        res = self.conn.fetchall()
        self.conn.close()
        return list(map(self._unsquish_tags, res))

    def clear_problemset(self, contest_id=None):
        self.conn = self.connection.cursor()

        if contest_id is None:
            query = 'DELETE FROM problem2'
            self.conn.execute(query)
        else:
            query = 'DELETE FROM problem2 WHERE contest_id = %s'
            self.conn.execute(query, (contest_id,))
        self.conn.close()

    def fetch_problemset(self, contest_id):
        self.conn = self.connection.cursor()

        query = ('SELECT contest_id, problemset_name, txtIndex, name, type, points, rating, tags '
                 'FROM problem2 '
                 'WHERE contest_id = %s')
        self.conn.execute(query, (contest_id,))
        res = self.conn.fetchall()
        self.conn.close()
        return list(map(self._unsquish_tags, res))

    def problemset_empty(self):
        self.conn = self.connection.cursor()

        query = 'SELECT 1 FROM problem2'
        self.conn.execute(query)
        res = self.conn.fetchone()
        self.conn.close()
        return res is None

    def reset_rating_change(self):
        self.conn = self.connection.cursor()

        query = 'TRUNCATE TABLE rating_change'
        self.conn.execute(query)
        self.conn.close()

    def close(self):
        self.conn.close()