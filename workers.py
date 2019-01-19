from queue import Empty
from threading import Thread, Event
from time import sleep
from protocol import DownloadFail


class Worker(Thread):
    def __init__(self, handler, logger, name=None):
        Thread.__init__(self)
        self.shutdown_flag = Event()
        self._handler = handler
        self._logger = logger
        self._name = name or str(self.ident)
        self.data = []

    def run(self):
        self._logger.info('Worker {} started'.format(self._name))
        while not self.shutdown_flag.is_set():
            self._handler()
        self._logger.info('Worker {} stopped'.format(self._name))


class QueueWorker(Worker):
    def __init__(self, handler, logger, task_queue, watcher, name=None):
        super().__init__(handler, logger, name)
        self.__task_queue = task_queue
        self.__watcher = watcher

    def run(self):
        self._logger.info('QueueWorker {} started'.format(self._name))
        while not self.shutdown_flag.is_set():
            try:
                task = self.__task_queue.get(timeout=1)
                if not task:
                    break
                result = self._handler(self.__task_queue, task)
                if result:
                    self.__watcher.data.append(result)
            except DownloadFail:
                self.__watcher.shutdown_flag.set()
                break
            except Empty:
                break
        self._logger.info('QueueWorker {} stopped'.format(self._name))


class Watcher(Worker):
    def __init__(self, logger, fail_handler, routine_function=None):
        super().__init__(lambda: None, logger, 'watcher')
        self.__fail_handler = fail_handler
        self.__routine_function = routine_function

    def run(self):
        self._logger.info('Watcher {} started'.format(self._name))
        while not self.shutdown_flag.is_set():
            sleep(0.1)
            if self.__routine_function:
                self.__routine_function(self)
        self.__fail_handler()
        self._logger.info('Watcher {} stopped'.format(self._name))
