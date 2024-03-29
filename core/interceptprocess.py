from subprocess import Popen, PIPE
from typing import Union
import os
from core import parser, base, intercept

class InterceptProcess:

    def __init__(self, base:base.Base, parser:parser.Parser) -> None:
        """Initiate subprocesses

        Args:
            base (base.Base): Current Intance of Base class
            parser (parser.Parser): Current Instance of Parser class
        """

        self.subprocess:list[Popen[bytes]] = []
        self.subprocess_detail:dict = {}

        self.Parser = parser
        self.Base = base

        self.init_processes()
        self.create_threads_for_processes()

        return None

    def init_processes(self) -> None:

        isJournalctl = False            # Verifier si un process journal doit etre lancé
        module_names_with_single_subprocess = []

        for mod_name in self.Parser.module_names:
            # proc = ["sshd","dovecot","proftpd"]
            if 'source_log' in self.Parser.modules[mod_name]:
                # Run subprocess with log source location
                source_log = self.Parser.modules[mod_name]['source_log']
                subprocess = self._create_subprocess(source_log)
                self.subprocess_detail[mod_name] = subprocess
            else:
                # Run subprocess with journalctl -f
                isJournalctl = True
                module_names_with_single_subprocess.append(mod_name)

        if isJournalctl:
            subprocess = self._create_subprocess()
            for mod_name_ssprocess in module_names_with_single_subprocess:
                self.subprocess_detail[mod_name_ssprocess] = subprocess

        return None

    def _create_subprocess(self, logs_source:str=None) -> Union[Popen[bytes], None]:

        if logs_source is None:
            process = Popen(['journalctl', '-f'], stdout=PIPE, stderr=PIPE)
            self.subprocess.append(process)
            return process

        if not os.path.exists(logs_source):
            self.Base.log_print(f'{self._create_subprocess.__name__} - {logs_source} - no such directory or file','red')
            return None

        process = Popen(['tail', '-f','-n', '0', logs_source], stdout=PIPE, stderr=PIPE)

        self.subprocess.append(process)

        return process

    def create_threads_for_processes(self) -> None:
        """Execute every subprocess in a separate thread
        """

        for subprocess in self.subprocess:
            self.Base.create_thread(self._run_subprocess, (subprocess, ))

        return None

    def _run_subprocess(self, subprocess:Popen[bytes]) -> None:

        Intercept = intercept.Intercept(self.Base, self.Parser, subprocess, self.subprocess_detail)

        while True:
            output = subprocess.stdout.readline().decode('utf-8').strip()
            if output:
                Intercept.run_process(output)
                if self.Base.DEBUG:
                    print(output)

    def close_interceptor(self) -> None:
        """close interceptor
        """

        self.Base.clean_iptables()                      # We clean iptables and iptables local table

        for subprocess in self.subprocess:
            self.Base.log_print(f'Terminate subprocess {subprocess}', 'green')
            subprocess.terminate()

        return None