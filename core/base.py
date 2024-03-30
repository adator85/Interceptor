from subprocess import run, PIPE
import os, threading, time, socket, json, requests
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Engine, Connection, CursorResult
from sqlalchemy.sql import text
from platform import python_version
from typing import Union

class Base:
    '''### Class contain all the basic methods
    - Global Interceptor default variables
    - All datetime methods needed by Interceptor
    - database connections
    - Thread creation methods
    - database cleaning methods
    - iptables cleaning methods
    - Abuseipdb interactions methods
    '''

    __COLORS:dict = {'white': '\033[97m', 
                'green': '\033[92m', 
                'red': '\033[91m',
                'yellow': '\033[93m',
                'reset':'\033[0m'
                }

    def __init__(self) -> None:

        self.VERSION                = '2.1.0'                                   # MAJOR.MINOR.BATCH
        self.CURRENT_PYTHON_VERSION = python_version()                          # Current python version
        self.DATE_FORMAT            = '%Y-%m-%d %H:%M:%S'                       # The date format
        self.HOSTNAME               = socket.gethostname()                      # Hostname of the local machine
        self.IPV4                   = socket.gethostbyname(self.HOSTNAME)       # Local ipv4 of the local machine
        self.PULSE                  = 5                                         # Pulse in seconds
        self.DEBUG                  = False                                     # Debug variable pour afficher les outputs
        self.default_attempt        = 4                                         # Default attempt before jail
        self.default_jail_duration  = 120                                       # Default Duration in seconds before the release
        self.default_ipv4           = '0.0.0.0'                                 # Default ipv4 to be used by Interceptor

        self.api:dict               = {}                                        # Available API's configuration from global.json

        self.default_intcHQ_active    = False                                   # Use head quarter information
        self.default_intcHQ_report    = False                                   # Report to the HQ intrusions
        self.default_intcHQ_timeout   = 5                                       # HQ Timeout
        self.default_intcHQ_jail_totalReports = 10                              # HQ jail the customer where total reports is greather than default total reports
        self.default_intcHQ_jail_abuseipdb_score = 100                          # Default score for the jail if not set in the configuration
        self.default_intcHQ_jail_duration = 600                                 # Default HQ duration jail

        self.lock = threading.RLock()                                           # Define RLock for multithreading
        self.hb_active:bool = True                                              # Define heartbeat variable
        self.running_threads:list[threading.Thread] = []                        # Define running_threads variable

        self.logs_init()                                                        # Init logs directory and log file.
        self.engine, self.cursor = self.db_init()                               # Init Engine & Cursor
        self.__db_create_tables()                                               # Create tables

        return None

    def get_unixtime(self)->int:
        """Get Unixtime in int format

        Returns:
            int: Current time in seconds
        """
        unixtime = int( time.time() )
        return unixtime

    def get_datetime(self) -> datetime:
        """Get datetime object

        Returns:
            datetime: datetime object
        """
        return datetime.now()

    def get_sdatetime(self) -> str:
        """Get datetime in string format defined by self.DATE_FORMAT

        Returns:
            str: date in string format
        """
        currentdate = datetime.now().strftime(self.DATE_FORMAT)
        return currentdate

    def convert_to_datetime(self, datetime_text:str) -> datetime:
        """Convertir un datetime de type text en type datetime object

        Args:
            datetime_text (str): la date et l'heure a convertir

        Returns:
            datetime: datetime object
        """
        conveted_datetime = datetime.strptime(datetime_text, self.DATE_FORMAT)

        return conveted_datetime

    def minus_one_hour(self, hours:float) -> str:
        """Deduct hours from the current datetime

        Args:
            hours (float): How many hours you want to deduct from the current datetime

        Returns:
            str: the datetime minus the hour passed in the global format
        """
        # '17-02-2024 19:26:16'
        current_datetime = datetime.now()
        result_datetime = current_datetime - timedelta(hours=hours)

        result_datetime = result_datetime.strftime(self.DATE_FORMAT)

        return result_datetime

    def add_secondes_to_date(self, date_time:datetime, seconds_duration:int) -> datetime:
        """Add seconds to the datetime

        Args:
            date_time (datetime): datetime you want to increment
            seconds_duration (int): the seconds you want to add

        Returns:
            datetime: The datetime + the seconds
        """
        result = date_time + timedelta(seconds=seconds_duration)

        return result

    def db_init(self) -> tuple[Engine, Connection]:
        """Initiat DB Connexion

        Returns:
            tuple[Engine, Connection]: tuple with Engine and Connection objects
        """
        db_directory = f'db{os.sep}'
        db_full_path = f'{db_directory}software.db'

        if not os.path.exists(f'{db_directory}'):
            os.makedirs(db_directory)

        engine = create_engine(f'sqlite:///{db_full_path}', echo=False)
        cursor = engine.connect()

        return engine, cursor

    def db_execute_query(self, query:str, params:dict = {}) -> CursorResult:
        """Execute a sql query

        Args:
            query (str): The query you want to perform
            params (dict, optional): The param you want to add to the query. Defaults to {}.

        Returns:
            CursorResult: The object CursorResult
        """
        with self.lock:
            insert_query = text(query)
            if not params:
                response = self.cursor.execute(insert_query)
            else:
                response = self.cursor.execute(insert_query, params)

            self.cursor.commit()

            return response

    def __db_create_tables(self) -> None:

        table_logs = f'''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            createdOn TEXT,
            intrusion_service_id TEXT,
            intrusion_detail TEXT,
            module_name TEXT,
            ip_address TEXT,
            keyword TEXT,
            user TEXT
            )
        '''

        table_iptables = f'''CREATE TABLE IF NOT EXISTS iptables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            createOn TEXT,
            module_name TEXT,
            ip_address TEXT,
            duration INTEGER
            )
        '''

        table_iptables_logs = f'''CREATE TABLE IF NOT EXISTS iptables_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            createdOn TEXT,
            module_name TEXT,
            ip_address TEXT,
            duration INTEGER
            )
        '''

        self.db_execute_query(table_logs)
        self.db_execute_query(table_iptables)
        self.db_execute_query(table_iptables_logs)

        return None

    def db_record_ip(self, service_id:str, intrusion_detail:str, module_name:str, ip:str, keyword:str, user:str) -> int:
        """Record an ip into the logs table

        Args:
            service_id (str): The service id
            module_name (str): The module name
            ip (str): The remote ip address
            keyword (str): The keyword
            user (str): The user attempt

        Returns:
            int: The number of rows affected
        """
        query = '''INSERT INTO logs (createdOn, intrusion_service_id, intrusion_detail, module_name, ip_address, keyword, user) 
                VALUES (:datetime,:intrusion_service_id, :intrusion_detail, :module_name, :ip, :keyword, :user)
                '''
        mes_donnees = {
                        'datetime': self.get_sdatetime(),
                        'intrusion_service_id': service_id,
                        'intrusion_detail': intrusion_detail,
                        'module_name':module_name,
                        'ip': ip,
                        'keyword':keyword,
                        'user':user
                        }

        r = self.db_execute_query(query, mes_donnees)

        return r.rowcount

    def db_record_iptables(self, module_name:str, ip:str, duration:int) -> int:
        """Record the remote ip address into the iptables table

        Args:
            module_name (str): The module name
            ip (str): The remote ip address
            duration (int): The ban duration

        Returns:
            int: The number of rows affected
        """
        query = '''INSERT INTO iptables (createdOn, module_name, ip_address, duration) 
                VALUES (:datetime, :module_name, :ip, :duration)
                '''
        mes_donnees = {
                        'datetime': self.get_sdatetime(),
                        'module_name':module_name,
                        'ip': ip,
                        'duration':duration
                        }

        r = self.db_execute_query(query, mes_donnees)
        return r.rowcount

    def db_record_iptables_logs(self, module_name:str, ip:str, duration:int) -> int:
        """Record the remote ip address that has been jailed

        Args:
            module_name (str): The module name
            ip (str): The remote ip address
            duration (int): The duration of the jail

        Returns:
            int: The number of rows affected
        """
        query = '''INSERT INTO iptables_logs (createdOn, module_name, ip_address, duration) 
                VALUES (:datetime, :module_name, :ip, :duration)
                '''
        mes_donnees = {
                        'datetime': self.get_sdatetime(),
                        'module_name':module_name,
                        'ip': ip,
                        'duration':duration
                        }

        r = self.db_execute_query(query, mes_donnees)
        return r.rowcount

    def db_remove_iptables(self, ip:str) -> int:
        """Remove remote ip address from the iptables table
        when the jail duration expire

        Args:
            ip (str): The remote ip address

        Returns:
            int: The number of rows affected
        """
        query = '''DELETE FROM iptables WHERE ip_address = :ip'''

        mes_donnees = {'ip': ip}

        r = self.db_execute_query(query, mes_donnees)

        return r.rowcount

    def logs_init(self) -> None:
        """Create logs directory if not available
        """
        logs_directory = f'logs{os.sep}'
        logs_full_path = f'{logs_directory}intercept.log'

        if not os.path.exists(f'{logs_directory}'):
            os.makedirs(logs_directory)
            with open(logs_full_path, 'a+') as log:
                log.write(f'{self.get_sdatetime()} - Interceptor Init logs\n')

        return None

    def log_print(self, string:str, color:str = None) -> None:
        """Print logs in the terminal and record it in a file

        Args:
            string (str): the log message
            color (str): the color to be used in the terminal
        """
        reset = self.__COLORS['reset']
        isExist_color = False

        if color is None:
            print(f'{self.get_sdatetime()}: {string}')

        for key_color, value_color in self.__COLORS.items():
            if key_color == color:
                print(f'{value_color}{self.get_sdatetime()}: {string}{reset}')
                isExist_color = True

        if not isExist_color:
            print(f'{self.get_sdatetime()}: {string}')

        logs_directory = f'logs{os.sep}'
        logs_full_path = f'{logs_directory}intercept.log'

        with open(logs_full_path, 'a+') as log:
            log.write(f'{self.get_sdatetime()}: {string}\n')
            log.close()

        return None

    def create_thread(self, func:object, func_args: tuple = (), func_name:str ='') -> None:
        try:
            current_func_name = func.__name__

            th = threading.Thread(target=func, args=func_args, name=str(current_func_name), daemon=True)
            th.start()

            self.running_threads.append(th)
            self.log_print(f"Thread ID : {str(th.ident)} | Thread name : {th.getName()} | Function name: {str(func_name)} | Running Threads : {len(threading.enumerate())}", "green")

        except AssertionError as ae:
            self.log_print(f'Assertion Error -> {ae}', 'red')

    def heartbeat(self, beat:float) -> None:
        """Run periodic action every {beat} seconds
        this method must be run in a thread

        Args:
            beat (float): Duration between every action
        """
        while self.hb_active:
            time.sleep(beat)
            self.clean_iptables()

        return None

    def get_no_filters_files(self) -> int:

        path = f'modules{os.sep}'
        no_files = 0

        list_files_in_directory = os.listdir(path)

        for file in list_files_in_directory:
            if file.endswith('.json'):
                no_files += 1

        return no_files

    def clean_iptables(self) -> None:
        """Clean iptables db table and iptables
        release remote ip address when the duration is expired
        """
        query = f'''SELECT ip_address, createdOn, duration, module_name 
                    FROM iptables
                '''

        cursorResult = self.db_execute_query(query)
        r = cursorResult.fetchall()

        for result in r:
            db_ip, db_datetime, db_duration, db_module_name = result
            datetime_object = self.convert_to_datetime(db_datetime)
            dtime_final = self.add_secondes_to_date(datetime_object, db_duration)

            if self.get_datetime() > dtime_final:
                self.db_remove_iptables(db_ip)
                self.ip_tables_remove(db_ip)
                self.log_print(f'{db_module_name} - "{db_ip}" - released from jail', 'green')

    def clean_db_logs(self) -> bool:
        """Clean logs that they have more than 24 hours
        """
        response = False
        query = "DELETE FROM logs WHERE ip_address = :ip"
        mes_donnees = {'ip': self.default_ipv4}
        default_ip_request = self.db_execute_query(query,mes_donnees)

        query = '''DELETE FROM logs WHERE createdOn <= :datetime'''
        mes_donnees = {'datetime': self.minus_one_hour(24)}
        r_datetime = self.db_execute_query(query, mes_donnees)

        affected_rows = r_datetime.rowcount
        affected_rows_default_ipv4 = default_ip_request.rowcount
        affected = affected_rows + affected_rows_default_ipv4

        if affected > 0:
            self.log_print(f'clean_db_logs - Deleted : Logs {str(affected_rows)} - Default ip {affected_rows_default_ipv4}','green')
            response = True

        return response

    def ip_tables_add(self, module_name:str, ip:str, duration_seconds:int) -> int:

        if self.ip_tables_isExist(ip):
            return 0

        system_command = '/sbin/iptables -A INPUT -s {} -j REJECT'.format(ip)
        os.system(system_command)
        rowcount = self.db_record_iptables(module_name, ip, duration_seconds)
        self.db_record_iptables_logs(module_name, ip, duration_seconds)
        return rowcount

    def ip_tables_remove(self, ip:str) -> None:

        system_command = '/sbin/iptables -D INPUT -s {} -j REJECT'.format(ip)
        os.system(system_command)
        return None

    def ip_tables_reset(self) -> None:

        system_command = '/sbin/iptables -F'
        os.system(system_command)
        return None

    def ip_tables_isExist(self, ip:str) -> bool:
        """Vérifie si une ip existe dans iptables

        Args:
            ip (str): l'adresse ip

        Returns:
            bool: True si l'ip existe déja
        """

        # check_rule = run(['/sbin/iptables','-C','INPUT','-s',ip,'-j','REJECT'],stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
        check_rule = run(['/sbin/iptables','-C','INPUT','-s',ip,'-j','REJECT'],stdout=PIPE, stderr=PIPE).returncode == 0
        response = False

        if check_rule:
            response = True

        return response

    def get_information_from_HQ(self, ip_address: str) -> Union[dict, None]:

        try:
            api_name        = 'intc_hq'

            if not api_name in self.api:
                return None
            elif not self.api[api_name]['active']:
                return None
            elif not self.api[api_name]['report']:
                return None
            elif ip_address == self.default_ipv4:
                return None

            url = f"{self.api[api_name]['url']}check/" if 'url' in self.api[api_name] else None
            api_key = self.api[api_name]['api_key'] if 'api_key' in self.api[api_name] else None

            if url is None:
                return None

            url = url + ip_address

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'user-agent': 'Interceptor Client',
                'Key': api_key
            }

            response = requests.request(method='GET', url=url, headers=headers, timeout=self.default_intcHQ_timeout)

            # Formatted output
            req = json.loads(response.text)

            if 'code' in req:
                if not req['error']:
                    if self.DEBUG:
                        self.log_print(f"INTC_HQ RECEIVE INFORMATION - {ip_address} --> {str(req['code'])} {req['message']}", "green")
                else:
                    self.log_print(f"INTC_HQ RECEIVE INFORMATION - {ip_address} --> {str(req['code'])} {req['message']}", "red")

            return req

        except KeyError as ke:
            self.log_print(f'API Error KeyError : {ke}','red')
            return None
        except TypeError as te:
            self.log_print(f'API Error TypeError : {te}','red')
            return None
        except requests.ReadTimeout as timeout:
            self.log_print(f'API Error Timeout : {timeout}','red')
            return None
        except requests.ConnectionError as ConnexionError:
            if self.DEBUG:
                self.log_print(f'API Connection Error : {ConnexionError}','red')
            return None

        return None

    def report_to_HQ(self, intrusion_datetime:str, intrusion_detail:str, ip_address:str, intrusion_service_id:str, module_name:str, keyword:str) -> None:

        try:
            api_name        = 'intc_hq'

            if not api_name in self.api:
                return None
            elif not self.api[api_name]['active']:
                return None
            elif not self.api[api_name]['report']:
                return None
            elif ip_address == self.default_ipv4:
                return None

            url = f"{self.api[api_name]['url']}report/" if 'url' in self.api[api_name] else None
            api_key = self.api[api_name]['api_key'] if 'api_key' in self.api[api_name] else None

            if url is None:
                return None

            querystring = {
                'intrusion_datetime': intrusion_datetime,
                'intrusion_detail': intrusion_detail,
                'intrusion_service_id': str(intrusion_service_id),
                'ip_address': ip_address,
                'reported_hostname': self.HOSTNAME,
                'module_name': module_name,
                'keyword': keyword
            }

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'user-agent': 'Interceptor Client',
                'Key': api_key
            }

            response = requests.request(method='POST', url=url, headers=headers, timeout=self.default_intcHQ_timeout, json=querystring)

            # Formatted output
            req = json.loads(response.text)

            if 'code' in req:
                if req['code'] == 200:
                    if self.DEBUG:
                        self.log_print(f"INTC_HQ REPORTED - {ip_address} --> {str(req['code'])} {req['message']}", "green")
                else:
                    self.log_print(f"INTC_HQ RESPONSE - {ip_address} - {str(req['code'])} {req['message']}", "red")

            return None

        except KeyError as ke:
            self.log_print(f'API Error KeyError : {ke}','red')
        except TypeError as te:
            self.log_print(f'API Error TypeError : {te}','red')
        except requests.ReadTimeout as timeout:
            self.log_print(f'API Error Timeout : {timeout}','red')
        except requests.ConnectionError as ConnexionError:
            if self.DEBUG:
                self.log_print(f'API Connection Error : {ConnexionError}','red')

        return None
