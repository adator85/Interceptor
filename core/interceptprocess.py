from subprocess import Popen, PIPE
from typing import Union
import os
from core import parser, base, intercept

class InterceptProcess:

    def __init__(self, base:base.Base, parser:parser.Parser) -> None:
        # Initialiser les processus

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
            process = Popen(['journalctl', '-f', '-n', '0'], stdout=PIPE, stderr=PIPE)
            self.subprocess.append(process)
            return process

        if not os.path.exists(logs_source):
            self.Base.logs.critical(f'{self._create_subprocess.__name__} - {logs_source} - no such directory or file')
            return None

        process = Popen(['tail', '-f','-n', '0', logs_source], stdout=PIPE, stderr=PIPE)

        self.subprocess.append(process)

        return process

    def create_threads_for_processes(self) -> None:
        """Execute chaque subprocess dans un thread séparé
        """

        for subprocess in self.subprocess:
            self.Base.create_thread(self._run_subprocess, func_args=(subprocess, ), func_name=str(subprocess.args))

        return None

    def _run_subprocess(self, subprocess:Popen[bytes]) -> None:

        Intercept = intercept.Intercept(self.Base, self.Parser, subprocess, self.subprocess_detail)

        while True:
            output = subprocess.stdout.readline().decode('utf-8').strip()
            if output:
                Intercept.run_process(output)
                self.Base.logs.debug(f'raw: {output}')
