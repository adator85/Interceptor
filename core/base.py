from subprocess import run, PIPE
import os, sys, threading, time, socket, json, requests, logging
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

    def __init__(self) -> None:

        if not self.is_root():
            print('/!\\ Interceptor must be executed as root /!\\')
            sys.exit(1)

        self.appConfig = self.__load_app_config()

        self.VERSION                = self.getAppConfig('version')              # MAJOR.MINOR.BATCH
        self.DEBUG_LEVEL            = self.getAppConfig('debug_level')          # Debug variable pour afficher les outputs
        self.PULSE                  = self.getAppConfig('pulse')                # Pulse in seconds
        self.hq_communication_freq  = self.getAppConfig('hq_communication_freq')# Frequency in seconds to send data to HQ
        self.default_attempt        = self.getAppConfig('jail_attempt')         # Default attempt before jail
        self.default_jail_duration  = self.getAppConfig('jail_duration')        # Default Duration in seconds before the release

        self.CURRENT_PYTHON_VERSION = python_version()                          # Current python version
        self.HOSTNAME               = socket.gethostname()                      # Hostname of the local machine
        self.IPV4                   = socket.gethostbyname(self.HOSTNAME)       # Local ipv4 of the local machine

        self.DATE_FORMAT            = '%Y-%m-%d %H:%M:%S'                       # The date format
        self.api:dict               = {}                                        # Available API's configuration from global.json
        self.default_ipv4           = "0.0.0.0"                                 # Default ipv4 to be used by Interceptor

        self.global_whitelisted_ip:list     = []                                # Global Whitelisted ip
        self.local_whitelisted_ip:list      = []                                # Local whitelisted ip (by modules)
        self.whitelisted_ip:list            = []                                # All white listed ip (global and local)

        self.default_intcHQ_active    = False                                   # Use head quarter information
        self.default_intcHQ_report    = False                                   # Report to the HQ intrusions
        self.default_intcHQ_timeout   = 30                                      # HQ Timeout
        self.default_intcHQ_jail_totalReports = 10                              # HQ jail the customer where total reports is greather than default total reports
        self.default_intcHQ_jail_abuseipdb_score = 100                          # Default score for the jail if not set in the configuration
        self.default_intcHQ_jail_duration = 600                                 # Default HQ duration jail

        self.lock = threading.RLock()                                           # Define RLock for multithreading
        self.hb_active:bool = True                                              # Define heartbeat variable
        self.running_threads:list[threading.Thread] = []                        # Define running_threads variable

        self.init_log_system()                                                  # Init log system

        self.CHAIN_NAME = "INTERCEPTOR"                                         # Define the iptables chain name
        self.iptables_chain_create()                                            # Create the iptables chain

        self.engine, self.cursor = self.db_init()                               # Init Engine & Cursor
        self.__db_create_tables()                                               # Create tables

        self.logs.debug(f"Module Base Initiated")

        return None

    def __load_app_config(self) -> dict[str, str]:
        """Load the main configuration of the app

        Returns:
            dict[str, str]: The key and the value of the configuration
        """

        filename = f'core{os.sep}configuration.json'
        app_configuration:dict[str, str] = {}

        with open(filename, 'r') as configuration:
            app_configuration = json.load(configuration)

        return app_configuration

    def getAppConfig(self, key: str) -> Union[str, int]:

        config = self.appConfig

        response = config.get(key)

        return response

    def init_log_system(self) -> None:
        """Init system logging
        - Initiat logging library
        - Create logs folder if not available
        - Configure the logs attribut
        """
        # Create folder if not available
        logs_directory = f'logs{os.sep}'
        if not os.path.exists(f'{logs_directory}'):
            os.makedirs(logs_directory)

        # Init logs object
        self.logs = logging
        self.logs.basicConfig(level=self.DEBUG_LEVEL,
                              filename='logs/interceptor.log',
                              format='%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s - %(message)s')

        self.logs.debug("-" * 16)

        return None

    def is_root(self) -> bool:
        """Check if the code is running by a root user

        Returns:
            bool: True if root
        """
        if os.geteuid() == 0:
            return True
        else:
            return False

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

    def convert_to_integer(self, value):
        """Convertit la valeur reçue en entier, si possible.
        Sinon elle retourne la valeur initiale.

        Args:
            value (any): la valeur à convertir

        Returns:
            any: Retour un entier, si possible. Sinon la valeur initiale.
        """
        try:
            response = int(value)
            return response
        except ValueError:
            return value
        except TypeError:
            return value

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

    #################################
    # BEGINNING OF DATABASE METHODS #
    #################################

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

        self.logs.debug("Connexion to database ok")

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
            createdOn TEXT,
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

        table_hq_information = f'''CREATE TABLE IF NOT EXISTS hq_information (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            createdOn TEXT,
            updatedOn TEXT,
            ip_address TEXT,
            ab_score INTEGER,
            hq_totalReports INTEGER
            )
        '''

        table_hq_information_to_report = f'''CREATE TABLE IF NOT EXISTS hq_information_to_report (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            createdOn TEXT,
            id_log INTEGER
        )'''

        a = self.db_execute_query(table_logs)
        b = self.db_execute_query(table_iptables)
        c = self.db_execute_query(table_iptables_logs)
        d = self.db_execute_query(table_hq_information)
        e = self.db_execute_query(table_hq_information_to_report)

        creation = a.rowcount + b.rowcount + c.rowcount + d.rowcount + e.rowcount
        if creation > 0:
            self.logs.debug("Table creation OK")

        return None

    def db_record_ip(self, service_id:str, intrusion_detail:str, module_name:str, ip:str, keyword:str, user:str) -> bool:
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
        response = False
        current_datetime = self.get_sdatetime()
        query = '''INSERT INTO logs (createdOn, intrusion_service_id, intrusion_detail, module_name, ip_address, keyword, user) 
                VALUES (:datetime, :intrusion_service_id, :intrusion_detail, :module_name, :ip, :keyword, :user)
                '''
        mes_donnees = {
                        'datetime': current_datetime,
                        'intrusion_service_id': service_id,
                        'intrusion_detail': intrusion_detail,
                        'module_name':module_name,
                        'ip': ip,
                        'keyword':keyword,
                        'user':user
                        }

        r = self.db_execute_query(query, mes_donnees)
        row_affected_logs = r.rowcount
        lastLogId = r.lastrowid

        query_hq_info_to_report = 'INSERT INTO hq_information_to_report (createdOn, id_log) VALUES (:createdOn, :id_log)'
        lastLogId = lastLogId if type(self.convert_to_integer(lastLogId)) == int else 0
        query_data = {
            'createdOn': current_datetime,
            'id_log': lastLogId
        }

        row_affeced_hq = 0
        if lastLogId > 0:
            c = self.db_execute_query(query_hq_info_to_report, query_data)
            row_affeced_hq = c.rowcount

        if (row_affeced_hq + row_affected_logs) > 0:
            response = True

        self.logs.info(f'{module_name} - {keyword} - {service_id} - {ip} - {user} - recorded')

        return response

    def db_record_hq_information(self, ip_address:str, ab_score:int, hq_totalReports:int) -> bool:

        response = False
        createdOn = self.get_sdatetime()
        ab_score:int = ab_score if type(self.convert_to_integer(ab_score)) == int else 0
        hq_totalReports:int = hq_totalReports if type(self.convert_to_integer(hq_totalReports)) == int else 0

        query = """INSERT INTO hq_information (createdOn, ip_address, ab_score, hq_totalReports) 
        VALUES (:createdOn, :ip_address, :ab_score, :hq_totalReports)
        """

        query_data = {
            'createdOn': createdOn,
            'ip_address': ip_address,
            'ab_score': ab_score,
            'hq_totalReports': hq_totalReports
        }

        r = self.db_execute_query(query, query_data)

        if r.rowcount > 0:
            response = True

        return response

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
        rowcount = r.rowcount

        return rowcount

    def clean_db_logs(self) -> bool:
        """Clean logs that they have more than 24 hours
        """
        response = False
        query = "DELETE FROM logs WHERE ip_address = :ip"
        query_hq_information = "DELETE FROM hq_information WHERE ip_address = :ip"
        mes_donnees = {'ip': self.default_ipv4}
        default_ip_request = self.db_execute_query(query,mes_donnees)

        # Clean whitelisted ip from the database
        affected_whitelisted_ip = 0
        for whitelisted_ip in self.whitelisted_ip:
            my_data = {'ip': whitelisted_ip}
            whitelisted_fetch = self.db_execute_query(query, my_data)
            affected_whitelisted_ip += whitelisted_fetch.rowcount

            whitelisted_fetch_hq = self.db_execute_query(query_hq_information, my_data)
            affected_whitelisted_ip += whitelisted_fetch_hq.rowcount

        query_hq_info_to_report = """SELECT 
                        hir.id as 'id',
                        l.ip_address as 'ip_address'
                    FROM hq_information_to_report hir
                    LEFT JOIN logs l ON l.id = hir.id_log
                    WHERE l.id IS NULL
                    """
        hq_info_to_report_fetch = self.db_execute_query(query_hq_info_to_report)
        query_delete = "DELETE FROM hq_information_to_report WHERE id = :id"

        affected_ip_to_report = 0
        for record in hq_info_to_report_fetch.fetchall():
            db_id, db_ip_address = record
            if db_ip_address is None:
                r_delete_to_report = self.db_execute_query(query_delete, {'id': db_id})
                affected_ip_to_report += r_delete_to_report.rowcount

        query = 'DELETE FROM logs WHERE createdOn <= :datetime'
        mes_donnees = {'datetime': self.minus_one_hour(24)}
        r_datetime = self.db_execute_query(query, mes_donnees)

        affected_rows = r_datetime.rowcount
        affected_rows_default_ipv4 = default_ip_request.rowcount
        affected = affected_rows + affected_rows_default_ipv4 + affected_whitelisted_ip + affected_ip_to_report

        if affected > 0:
            self.logs.info(f'clean_db_logs - Deleted : Logs {str(affected_rows)} | Default ip {affected_rows_default_ipv4} | WhiteListed IP {affected_whitelisted_ip} | Ip to report {affected_ip_to_report}')
            response = True

        return response

    # END OF DATABASE METHODS #

    ################################
    # BEGINNING OF THREADS METHODS #
    ################################

    def create_thread(self, func:object, func_args: tuple = (), func_name:str ='') -> None:
        try:
            current_func_name = func.__name__

            th = threading.Thread(target=func, args=func_args, name=str(current_func_name), daemon=True)
            th.start()

            self.running_threads.append(th)
            self.logs.info(f"Thread ID : {str(th.ident)} | Thread name : {th.getName()} | Function name: {str(func_name)} | Running Threads : {len(threading.enumerate())}")

        except AssertionError as ae:
            self.logs.critical(f"Assertion Error -> {ae}")

    def heartbeat(self, beat:float) -> None:
        """Run periodic action every {beat} seconds
        this method must be run in a thread

        Args:
            beat (float): Duration between every action
        """
        while self.hb_active:
            time.sleep(beat)
            self.clean_iptables()
            self.logs.debug(f"Running Heartbeat every {beat} seconds")

        return None

    def get_no_filters_files(self) -> int:

        path = f'modules{os.sep}'
        no_files = 0

        list_files_in_directory = os.listdir(path)

        for file in list_files_in_directory:
            if file.endswith('.json'):
                no_files += 1

        return no_files

    # END OF THREADS METHODS #

    #################################
    # BEGINNING OF IPTABLES METHODS #
    #################################

    def iptables_chain_create(self) -> bool:
        """Create a chain for Interceptor
        """

        chain_name = self.CHAIN_NAME

        self.iptables_remove_existing_rules()

        # If chain_name equal to INPUT then do not create chain
        if chain_name == 'INPUT':
            self.logs.debug(f"Default chain [INPUT]")
            return False

        # Create the chain
        system_command = f'/sbin/iptables -N {chain_name}'
        os.system(system_command)
        self.logs.debug(f"Creating chain: [{chain_name}]")

        add_chain_to_input = f'/sbin/iptables -A INPUT -j {chain_name}'
        os.system(add_chain_to_input)
        self.logs.debug(f"Adding the chain [{chain_name}] to INPUT")

        self.logs.debug(f"Iptables chain [{chain_name}] created.")

        return True

    def iptables_chain_isExist(self, name:str) -> bool:
        """Check if the chain name exist or not

        Args:
            name (str): The name of the chain

        Returns:
            bool: True if the chain name already exist.
        """

        check_rule = run(['/sbin/iptables','-N', name],stdout=PIPE, stderr=PIPE).returncode == 0
        response = False

        if check_rule:
            response = True

        return response

    def iptables_count_interceptor_occurence(self) -> int:

        run_command = run(['/sbin/iptables', '-S'], capture_output=True, text=True)
        output = run_command.stdout.splitlines()
        number_of_occurence:list = []

        for int_occurence in output:
            if '-A INPUT -j INTERCEPTOR' in int_occurence:
                number_of_occurence.append(int_occurence)

        return len(number_of_occurence)

    def iptables_remove_existing_rules(self) -> bool:

        number_of_occurence = self.iptables_count_interceptor_occurence()
        chain_name = self.CHAIN_NAME

        for i in range(0, number_of_occurence):
            os.system(f'/sbin/iptables -D INPUT -j {chain_name}')

        return True

    def ip_tables_add(self, module_name:str, ip:str, duration_seconds:int) -> int:

        chain_name = self.CHAIN_NAME

        if self.ip_tables_isExist(ip):
            return 0

        system_command = f'/sbin/iptables -A {chain_name} -s {ip} -j REJECT'
        os.system(system_command)
        rowcount = self.db_record_iptables(module_name, ip, duration_seconds)
        self.db_record_iptables_logs(module_name, ip, duration_seconds)
        return rowcount

    def ip_tables_remove(self, ip:str) -> None:

        chain_name = self.CHAIN_NAME

        system_command = f'/sbin/iptables -D {chain_name} -s {ip} -j REJECT'
        os.system(system_command)
        return None

    def ip_tables_reset(self) -> None:

        chain_name = self.CHAIN_NAME

        # clean ip in the chain
        system_command = f'/sbin/iptables -F {chain_name}'
        os.system(system_command)
        self.logs.info(f"Removing IPs from chain: [{chain_name}]")

        # Delete existing rules
        self.iptables_remove_existing_rules()
        self.logs.info(f"Removing rules from INPUT: [{chain_name}]")

        # Remove chain
        system_command = f'/sbin/iptables -X {chain_name}'
        os.system(system_command)
        self.logs.info(f"Removing chain: [{chain_name}]")

        self.logs.info("iptables has been cleared")
        return None

    def ip_tables_isExist(self, ip:str) -> bool:
        """Vérifie si une ip existe dans iptables

        Args:
            ip (str): l'adresse ip

        Returns:
            bool: True si l'ip existe déja
        """
        chain_name = self.CHAIN_NAME
        # check_rule = run(['/sbin/iptables','-C','INPUT','-s',ip,'-j','REJECT'],stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
        check_rule = run(['/sbin/iptables','-C', chain_name,'-s', ip,'-j','REJECT'],stdout=PIPE, stderr=PIPE).returncode == 0
        response = False

        if check_rule:
            response = True

        return response

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
                self.logs.info(f'{db_module_name} - "{db_ip}" - released from jail')

        return None

    # END OF IPTABLES METHODS #

    def get_internal_hq_info(self, ip_address:str) -> Union[tuple[int, int], tuple[None, None]]:
        """Fetch local database to retrieve ab_score and hq_totalReports

        Args:
            ip_address (str): remote ip address

        Returns:
            Union[tuple[int, int], None]: (ab_score, hq_totalReports) or None
        """
        query = 'SELECT ab_score, hq_totalReports FROM hq_information WHERE ip_address = :ip_address'
        param_query = {'ip_address': ip_address}

        fetch_query = self.db_execute_query(query, param_query)
        result_query = fetch_query.fetchone()

        if not result_query is None:
            ab_score, hq_totalReports = result_query
            return ab_score, hq_totalReports
        else:
            return None, None

    def thread_report_to_HQ_v2(self) -> None:
        """### 1. Get data from local database
        ### 2. Send it to HQ every 1.5 seconds
        ### 3. Check whether the ip is in the table hq_information
        ###     3.1 Record the ip and the information received from HQ (if no record available)
        ###     3.2 Edit the information if the record is available
        ### 4. Delete the record from the local database
        """
        current_date = self.get_sdatetime()

        query_hq_info_to_report = '''SELECT 
                        l.id as 'id_log',
                        l.createdOn as 'log_createdOn',
                        l.intrusion_service_id,
                        l.intrusion_detail,
                        l.module_name,
                        l.ip_address,
                        l.keyword
                    FROM hq_information_to_report hir
                    LEFT JOIN logs l ON l.id = hir.id_log
                    '''

        query_get_hq_info_select = 'SELECT id FROM hq_information WHERE ip_address = :ip_address'
        query_get_hq_info_insert = '''INSERT INTO hq_information (createdOn, updatedOn, ip_address, ab_score, hq_totalReports) 
        VALUES (:createdOn, :updatedOn, :ip_address, :ab_score, :hq_totalReports)
        '''
        query_get_hq_info_update = 'UPDATE hq_information SET ab_score = :ab_score, hq_totalReports = :hq_totalReports, updatedOn = :updatedOn WHERE ip_address = :ip_address'
        query_delete = 'DELETE FROM hq_information_to_report WHERE id_log = :id_to_delete'

        fetch_query = self.db_execute_query(query_hq_info_to_report)

        result_query = fetch_query.fetchall()
        if not result_query:
            return None

        for result in result_query:
            try:
                db_id_log, intrusion_date, intrusion_service_id, intrustion_detail, db_mod_name, db_ip_address, db_keyword = result

                # If ip is None then loop
                if db_ip_address is None:
                    continue

                # Report the information to HQ
                hq_response = self.report_to_HQ_v2(intrusion_date, intrustion_detail, db_ip_address, intrusion_service_id, db_mod_name, db_keyword)

                if hq_response is None or not hq_response:
                    continue

                if not 'ab_score' in hq_response and not 'hq_totalReports' in hq_response:
                    continue

                # Delete the record from local db
                query_data = {'id_to_delete': db_id_log}
                self.db_execute_query(query_delete, query_data)

                ab_score:int = hq_response['ab_score'] if type(self.convert_to_integer(hq_response['ab_score'])) == int else 0
                hq_totalReports:int = hq_response['hq_totalReports'] if type(self.convert_to_integer(hq_response['hq_totalReports'])) == int else 0

                # Check if ip is available locally
                param_get_hq_info_select = {'ip_address': db_ip_address}
                fetch_is_ip_available = self.db_execute_query(query_get_hq_info_select, param_get_hq_info_select)
                result_is_ip_available = fetch_is_ip_available.fetchone()

                # if ip not available then record it
                if result_is_ip_available is None:
                    param_get_hq_info_insert = {'createdOn': current_date, 'updatedOn': current_date, 'ip_address': db_ip_address, 'ab_score': ab_score, 'hq_totalReports': hq_totalReports}
                    self.db_execute_query(query_get_hq_info_insert, param_get_hq_info_insert)

                # if ip is available then update the record
                else:
                    param_get_hq_info_update = {'ab_score': ab_score, 'hq_totalReports': hq_totalReports, 'updatedOn': current_date, 'ip_address': db_ip_address}
                    self.db_execute_query(query_get_hq_info_update, param_get_hq_info_update)

                time.sleep(1.5)

            except TypeError as te:
                self.logs.critical(f"Type Error: {te} | {hq_response}")
            except KeyError as ke:
                self.logs.critical(f"Key Error: {ke} | {hq_response}")

        return None

    def report_to_HQ_v2(self, intrusion_datetime:str, intrusion_detail:str, ip_address:str, intrusion_service_id:str, module_name:str, keyword:str) -> Union[dict, None]:
        """Send information to HQ to record the intrusion and receive back from the HQ
        2 information about the abuseipdb_score and hq total reports

        Args:
            intrusion_datetime (str): Intrusion datetime
            intrusion_detail (str): Intrusion full detail
            ip_address (str): the report ip address
            intrusion_service_id (str): The intrusion service id
            module_name (str): The module name
            keyword (str): The keyword captured

        Returns:
            Union[dict, None]: The dictionary with all information or None
        """

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

            url = f"{self.api[api_name]['url']}report_v2/" if 'url' in self.api[api_name] else None
            api_key = self.api[api_name]['api_key'] if 'api_key' in self.api[api_name] else None

            if url is None and api_key is None:
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

            if response.status_code in [404, 503]:
                self.logs.warn(f"INTC_HQ CODE {response.status_code}")
                return None

            # Formatted output
            # Expected response : {error: False, code: 200, message: "The message", ab_score: 100|None, hq_totalReports: 5}
            req = json.loads(response.text)

            api_error = bool(req['error'])
            api_code = int(req['code'])
            api_message = req['message']
            api_ab_score = req['ab_score']
            api_hq_totalReports = req['hq_totalReports']

            if 'error' in req:
                if api_error:
                    self.logs.error(f"INTC_HQ RESPONSE [{api_code}] - {ip_address} --> {api_message}")
                    return None
                else:
                    self.logs.info(f"INTC_HQ RESPONSE [{api_code}] - {ip_address} --> ab_score: {api_ab_score} | hq_reports: {api_hq_totalReports}")

            self.logs.debug(f"RECIEVED FROM HQ : {req}")

            return req

        except KeyError as ke:
            self.logs.critical(f'API Error KeyError : {ke}')
            return False
        except TypeError as te:
            self.logs.critical(f'API Error TypeError : {te}')
            return False
        except requests.ReadTimeout as timeout:
            self.logs.critical(f'API Error Timeout : {timeout}')
            return False
        except requests.ConnectionError as ConnexionError:
            self.logs.critical(f'API Connection Error : {ConnexionError}')
            return False
        except json.decoder.JSONDecodeError as jde:
            self.logs.critical(f'JSon Decoder Error : {jde}')
            return False

    def say_hello_to_hq(self) -> bool:

        try:
            api_name        = 'intc_hq'

            if not api_name in self.api:
                self.logs.error(f"{api_name} not found in self.api variable")
                return False
            elif not self.api[api_name]['active']:
                self.logs.error(f"The status of the API is set to : {self.api[api_name]['active']}")
                return False
            elif not self.api[api_name]['report']:
                self.logs.error(f"The status of the report API is set to : {self.api[api_name]['report']}")
                return False

            url = f"{self.api[api_name]['url']}hello/" if 'url' in self.api[api_name] else None
            api_key = self.api[api_name]['api_key'] if 'api_key' in self.api[api_name] else None

            if url is None:
                self.logs.error(f"The URL of the API is : {url}")
                return False
            
            url = url + self.VERSION

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'user-agent': 'Interceptor Client',
                'Key': api_key
            }

            response = requests.request(method='GET', url=url, headers=headers, timeout=self.default_intcHQ_timeout)

            if response.status_code in [404, 503]:
                self.logs.warn(f"INTC_HQ CODE {response.status_code}")
                return False

            # Formatted output
            req = json.loads(response.text)

            self.logs.info(f"INTC_HQ RESPONSE TO HELLO --> status {str(req['code'])} - {req['message']}")

            self.logs.debug(f"RECIEVED FROM HQ : {req}")

            return True

        except KeyError as ke:
            self.logs.critical(f'API Error KeyError : {ke}')
            return False
        except TypeError as te:
            self.logs.critical(f'API Error TypeError : {te}')
            return False
        except requests.ReadTimeout as timeout:
            self.logs.critical(f'API Error Timeout : {timeout}')
            return False
        except requests.ConnectionError as ConnexionError:
            self.logs.critical(f'API Connection Error : {ConnexionError}')
            return False
        except json.decoder.JSONDecodeError as jde:
            self.logs.critical(f'JSon Decoder Error : {jde}')
            return False

    def send_to_hq(self) -> None:

        try:
            api_name = 'intc_hq'
            api: dict = self.api.get(api_name) if type(self.api.get(api_name)) == dict else None

            if api is None:
                return None

            url = f"{api.get('url')}ping/"
            api_key = api.get('api_key')


            headers: dict[str, str] = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'user-agent': 'Interceptor Client',
                'Key': api_key
            }

            response = requests.request(method='GET', url=url, headers=headers, timeout=self.default_intcHQ_timeout)

            return None

        except AttributeError as ae:
            self.logs.error(f'Attribute error: {ae}')
