#!/usr/bin/python3
"""Dictionary CLI

Runs a shell program to add/update words in a database of dictionary words.
"""
import os
import io
import sys

from typing import Union
from getpass import getpass

from mysql import connector as db
from mysql.connector import errorcode
from mysql.connector.errors import Error


class Environ(dict):
    """Environment Variables Dictionary

    Reads local environ for environment variables. 
    If None, defaults to localhost root login.

    To override, create an `.env` file 
    with the following as `KEY=value` pairs:  
    MYSQL_HOST
    MYSQL_PORT,
    MYSQL_AUTH,
    MYSQL_USER,
    MYSQL_PASSWORD, 
    MYSQL_DATABASE
    """
    #: key map to environment variables
    __CONFIG_MAP = dict(
        host='MYSQL_HOST',
        port='MYSQL_PORT',
        user='MYSQL_USER',
        password='MYSQL_PASSWORD', 
        database='MYSQL_DATABASE',
        auth_plugin='MYSQL_AUTH')
    #: default root login
    _DEFAULT_ENV = dict(
        host='localhost',
        port=3306,
        user='root',
        password='Password',  # XXX: Plaintext password is lame...do better
        database='dictionary',
        auth_plugin='caching_sha2_password')
    
    def __init_subclass__(cls) -> None:
        # Construct subclass: dict
        return super().__init_subclass__()

    @classmethod
    # load environ from file
    def load(
        cls, 
        file: Union[io.TextIOWrapper, None] = None
    ) -> dict:
        """Load Environment Variables  

        If None, defaults to localhost root login.
        """
        # given an `.env` file, load env vars.
        if isinstance(file, io.TextIOWrapper):
            envvars = dict()
            for line in file.readlines():
                key, val = (
                    lambda line: line.strip().split('='))(line)
                envvars[key] = val
            # map given env vars to config
            env = cls(
                {key:envvars[val] for key, val in cls.__CONFIG_MAP.items()})
        # given no file, query local env
        elif file is None:
            envvars = [
                os.environ.get(v, 0) for v in cls.__CONFIG_MAP.values()]
            # If env vars found, map env to config
            if all(envvars):
                env = cls(
                    {key:os.getenv(val) for key, val in cls.__CONFIG_MAP.items()})
            # else populate with defaults
            else: env = cls(
                {key:val for key, val in cls._DEFAULT_ENV.items()})
        # else populate with defaults
        else: env = cls(
            {key:val for key, val in cls._DEFAULT_ENV.items()})
        # type cast port back to integer
        env.update(port=int(env.get('port')))
        return env


class ConnectionFailureError(Exception):
    """Base Exception for database connection failures"""
    def __init__(self, error: Error, message: str, *args: object) -> Exception:
        super().__init__(*args)
        self.__error: Error = error
        self.message: str = message
    
    def __str__(self) -> str:
        return self.message


class IncorrectLogin(ConnectionFailureError):
    """Login host, user and/or password is incorrect"""
    def __init__(self, error: Error) -> Exception:
        message = "Could not login to host with user/password provided."
        super().__init__(error, message)


class DatabaseNotFound(ConnectionFailureError):
    """Error raised when database does not exist"""
    def __init__(self, error: Error) -> Exception:
        message = error.msg
        super().__init__(error, message)


class AccessDenied(ConnectionFailureError):
    """Error raised when Access Denied to database"""
    def __init__(self, error: Error) -> Exception:
        message = error.msg
        super().__init__(error, message)


class Connect:
    """Database Connection Handler"""
    def __init__(self, credentials: dict) -> None:
        self.creds = credentials
        # 
    def __enter__(self):
        try:
            self.conn = db.connect(**self.creds)
            sys.stdout.write('Connected successfully.\n')
            return self.conn
            # --
        except Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                raise IncorrectLogin(err)
            elif err.errno == errorcode.ER_DBACCESS_DENIED_ERROR:
                raise AccessDenied(err)
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                raise DatabaseNotFound(err)
            else: raise err
        # 
    def __exit__(self, type, value, traceback):
        self.conn.close()
        sys.stdout.write('\nConnection closed.\n')


class Queries:
    """SQL Query Interface"""
    version = """SHOW VARIABLES like 'version';"""
    _select = """SELECT word FROM words WHERE word = %(word)s;"""
    _insert = """INSERT INTO words (word) VALUES (%(new_word)s);"""
    _update = """UPDATE words SET word = %(new_word)s WHERE word = %(word)s;"""
    _delete = """DELETE FROM words WHERE word = %(word)s;"""
    def __init__(self, connection, __dict = True) -> None:
        self.connection = connection
        self.cursor = connection.cursor(dictionary = __dict)
        try:    # test connection by version query
            self.__test()
        except: raise
    
    def __test(self) -> None:
        """test connection with version query"""
        self.cursor.execute(self.version)
        res = self.cursor.fetchone()
        sys.stdout.write(f"MySQL v{res['Value']}\n")
    
    # standard queries
    def select(self, word: str) -> Union[dict, None]:
        """Select a word from the dictionary"""
        self.cursor.execute(self._select, {'word': word})
        return self.cursor.fetchone()
    
    def insert(self, new_word: str) -> None:
        """Insert a word into the dictionary"""
        self.cursor.execute(self._insert, {'new_word': new_word})
        self.connection.commit()
    
    def update(self, word: str, new_word: str) -> None:
        """Update the dictionary with a new word"""
        self.cursor.execute(
            self._update, {'word': word, 'new_word': new_word})
        self.connection.commit()
    
    def delete(self, word: str) -> None:
        """Delete a word in the dictionary"""
        self.cursor.execute(self._delete, {'word': word})
        self.connection.commit()


class Shell:
    """Dictionary CLI"""
    title = "# ========== Dictionary ========== #"
    instr = "# Press CTRL+C to quit."
    def __init__(
        self, 
        env_file: str = None
    ) -> None:
        self._cnx = Connect
        self._sql = Queries
        self._env = Environ
        #: environment setup
        if env_file is not None:
            config = self._env.load(env_file)
        else:
            config = self._env.load()
        self.env = config
        #: running loop flag
        self.__running = False

    def login(self):
        """Login credentials"""
        default_db = 'dictionary'
        default_auth = 'caching_sha2_password'
        #: prompt for user login credentials
        # NOTE: run with -O for fast login
        if __debug__:
            self.login_prompt()
        else: self.auto_login()
        # TODO: filter login credentials
        #: host
        self.host = self._host
        #: port
        self.port = self._port
        #: username
        self.username = self._user
        #: password
        self.password = self._pass
        #: database
        self.database = self.env.get('database', default_db)
        #: authentication plugin
        self._auth = self.env.get('auth_plugin', default_auth)
        # returns credentials
        return dict(
            host=self.host, 
            port=self.port, 
            user=self.username, 
            password=self.password, 
            database=self.database, 
            auth_plugin=self._auth)
    
    def login_prompt(self):
        """Prompt user for login credentials"""
        try:
            self._host = input('What host to connect to (localhost): ')
            self._port = input('What port to connect to (3306): ')
            self._user = input('What user to connect to (root): ')
            self._pass = input('What password to connect with: ')
        except KeyboardInterrupt:
            raise
    
    def auto_login(self):
        """Skip login for debug purposes.  
        USAGE: python3 -O add_a_word.py
        
        NOTE: Password still required, but is hidden.
        """
        try:
            self._host = self.env.get('host')
            print(f"What host to connect to (localhost): {self._host}")
            self._port = self.env.get('port')
            print(f"What port to connect to (3306): {self._port}")
            self._user = self.env.get('user')
            print(f"What user to connect to (root): {self._user}")
            # input root password, hidden input
            self._pass = getpass("What password to connect with: ")
        except KeyboardInterrupt:
            raise
            
    def _init(self):
        """Display Program Banner"""
        print(self.title)
        print(self.instr)
    
    def _exit(self, exit_msg: str, exit_code: int):
        """Graceful exit"""
        exit_msg = f'{str(exit_msg)}\nExiting.'
        # TODO: exit_code default 0
        print(exit_msg)
        exit(exit_code)

    def run(self):
        try:
            self._init()
            credentials = self.login()
            with self._cnx(credentials) as conn:
                sql = self._sql(conn)
                self.__running = True
                # enter main program loop
                while self.__running:
                    try:
                        self._run(sql)
                    except:
                        self.__running = False
                        raise
        # Incorrect login credentials
        except IncorrectLogin as logout:
            self._exit(logout, 0)
        # MySQL connection errors
        except Error as err:
            self._exit(err, 1)
        # python exceptions
        except Exception as exc:
            self._exit(exc, 1)
        # user exit
        except KeyboardInterrupt as sigint:
            self._exit(sigint, 0)

    def _run(self, query):
        """Main Program loop"""
        term = input("What word do you want to add/change: ")
        response = query.select(term)
        if response is None:
            addnew = self._prompt(
                f"'{term}' not found. "
                "Would you like to add it to the dictionary?\n"
                "[y/n] ")
            if addnew:
                query.insert(term)
                print(f"{term} added to the dictionary.")
        else:
            update = self._prompt(
                f"Found: {response['word']}. "
                "Would you like to update this word?\n"
                "[y/n] ")
            if update:
                old_word = response['word']
                new_word = input(f"Update {old_word} as: ")
                query.update(old_word, new_word)
                print(f"Updated {old_word} to {new_word}")
    
    def _prompt(self, prompt: str) -> bool:
        """Prompt for user input"""
        user_input = input(prompt)
        while user_input not in ['y','Y','yes','Yes','n','N','no','No']:
            print("Please answer 'y' or 'yes' for yes, or 'n' or 'no' for no.")
            user_input = input(prompt)
        if user_input in ['y','Y','yes','Yes']: return True
        elif user_input in ['n','N','no','No']: return False


def main() -> None:
    """Main Program
    
    Specify an Environment Variables file with `--file` or `-f`
    Use file extension `.env` and populate with `KEY=value` pairs.  
    """
    import argparse
    # parse command line args for env file
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--file', '-f', type=open, default=None, 
        help='Specify environment file.')
    args = parser.parse_args()
    if args.file:
        print(f"Loading env from {args.file.name}")
        cli = Shell(env_file=args.file)
    elif os.path.exists('default.env'):
        print("Loading default env from file.")
        default_env = open('default.env','r')
        cli = Shell(env_file=default_env)
    else:
        print("Loading environment variables.")
        cli = Shell()
    cli.run()


if __name__ == '__main__':
    main()
