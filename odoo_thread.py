# -*- coding: utf-8 -*-

import threading
import time
import odoo
import logging

_logger = logging.getLogger(__name__)


class Odoo_Thread(object):
    _des = '线程生成，控制类'
    # 线程锁
    LOCK = threading.Lock()
    # 未运行的线程
    thread_list = []
    # 正在运行的线程
    running_thread = []
    # 线程是否出错
    is_failed = 0

    def __init__(self, dbname, table_name, user_id, retry_times=3, retry_delay=10, delay_time=4, over_callback=False, error_callback=False):
        """
        初始化进程管理类
        :param dbname: 数据库名称
        :param table_name: 表名
        :param user_id: 用户id
        :param over_callback: 所有任务结束时的回调函数
        :param error_callback: 任务失败时的回调函数，如果为空，默认错误后继续执行.如果error_callback=True,报错后结束执行
        """
        self.dbname = dbname
        self.table_name = table_name
        self.user_id = user_id

        self.over_callback = over_callback
        self.error_callback = error_callback
        self._Max_Running_Threads = 5  # 最大运行线程数
        self.retry_delay = retry_delay
        self.retry_times = retry_times
        self.delay_time = delay_time

    # 所有的进程是否跑完了
    @staticmethod
    def is_all_over():
        if Odoo_Thread.LOCK.acquire():
            if not Odoo_Thread.running_thread and not Odoo_Thread.thread_list:
                return True
            else:
                return False

    # 通过线程工厂生成线程
    def thread_factory(self, name_target):
        """
        线程工厂，生成对应名字的线程工厂
        :param name_target: {'thread_name':(target,args[],daemon)}
        :return: thread_list
        """
        if isinstance(name_target, dict):
            for key, val in name_target.items():
                if key == 'error_callback':
                    self.error_callback = val
                elif key == 'over_callback':
                    self.over_callback = val
                elif val and val[0]:
                    arg = val[1] if len(val) > 1 else {}
                    daemon = val[2] if len(val) > 2 else False
                    t = self.new_thread(dbname=self.dbname, table_name=self.table_name, user_id=self.user_id,
                                        retry_times=self.retry_times, retry_delay=self.retry_delay,
                                        delay_time=self.delay_time, target=val[0], args=arg)
                    t.setDaemon(daemon)
                    t.stop_callback(self._move_self_start_new, self)
                    self._put_thread(t)

    # 添加线程到线程集合中
    def _put_thread(self, t):
        if isinstance(t, MyThread):
            if t in Odoo_Thread.thread_list:
                _logger.warning(u'already exist')
                return True
            Odoo_Thread.thread_list.append(t)
            return True
        return False

    @staticmethod
    def _move_self_start_new(cls, t):
        if Odoo_Thread.LOCK.acquire():
            if t in Odoo_Thread.running_thread:
                Odoo_Thread.running_thread.remove(t)
                if len(Odoo_Thread.thread_list) > 0 and Odoo_Thread.is_failed == 0:
                    t_new = Odoo_Thread.thread_list.pop()
                    t_new.start()
                    Odoo_Thread.running_thread.append(t_new)
                elif len(Odoo_Thread.running_thread) == 0 and cls.over_callback and Odoo_Thread.is_failed == 0:
                    # 执行完成回调
                    if callable(cls.over_callback):
                        cls.over_callback()
                elif Odoo_Thread.is_failed != 0 and cls.error_callback and t.is_failed:
                    # TODO 失败回调，要保证一个失败后，所有未执行的线程都不执行，所有执行的线程尝试结束
                    if callable(cls.error_callback):
                        t = Odoo_Thread.new_thread(dbname=cls.dbname, table_name=cls.table_name, user_id=cls.user_id,
                                                   target=cls.error_callback, args=t.kwargs['args'])
                        t.start()
                    for i in Odoo_Thread.running_thread:
                        i.join(0.05)
                        time.sleep(0.05)
                    pass
            Odoo_Thread.LOCK.release()

    def start_all(self):
        if Odoo_Thread.LOCK.acquire():
            while True:
                if len(Odoo_Thread.thread_list) > 0:
                    t = Odoo_Thread.thread_list.pop()
                    t.start()
                    if len(Odoo_Thread.running_thread) < self._Max_Running_Threads:
                        Odoo_Thread.running_thread.append(t)
                    else:
                        # 释放线程锁
                        Odoo_Thread.LOCK.release()
                        break
                else:
                    # 释放线程锁
                    Odoo_Thread.LOCK.release()
                    break

    @staticmethod
    def new_thread(**kwargs):
        """
        生成thread 如果需要最后callback则加入到self.thread_list中
        :param dbname: 数据库名称 string
        :param table_name: module_name string 通过self._name获得
        :param user_id: 用户id int 通过self.env.user.id获得
        :param target:需要执行的方法，必须加上装饰器@classmethod
        :param args: target需要的参数
        :param callback:方法执行完毕后的回调函数
        :return: thread实例
        """

        def reback_target(kwargs):
            dbname = kwargs['dbname']
            table_name = kwargs['table_name']
            user_id = kwargs['user_id']
            target = kwargs['target']
            delay_time = 4
            if 'delay_time' in kwargs:
                delay_time = kwargs['delay_time']
            retry_times = 3
            if 'retry_times' in kwargs:
                retry_times = kwargs['retry_times']
            retry_delay = 10
            if 'retry_delay' in kwargs:
                retry_delay = kwargs['retry_delay']
            time.sleep(delay_time)
            cls = odoo.registry(dbname)[table_name]
            while retry_times >= 0:
                with cls.pool.cursor() as cr:
                    with odoo.api.Environment.manage():
                        try:
                            self = odoo.api.Environment(cr, user_id, {})[table_name]
                            if 'args' in kwargs:
                                target(self, **kwargs['args'])
                            else:
                                target(self)
                            retry_times = -1
                        except Exception, e:
                            cr.rollback()
                            _logger.error(e)
                            retry_times -= 1
                            if retry_times >= 0:
                                time.sleep(retry_delay)
                            else:
                                Odoo_Thread.is_failed += 1
                                raise e

        return MyThread(target=reback_target, args=(kwargs,))


# 修改了一点点的线程，为了能够自动从队列里去除自己，并加入新成员
class MyThread(threading.Thread):
    def __init__(self, **kwargs):
        super(MyThread, self).__init__(**kwargs)
        self.callback = False
        self.thread_contral = False
        self.is_failed = False
        self.kwargs = kwargs['args'][0]

    def run(self):
        try:
            super(MyThread, self).run()
        except Exception:
            self.is_failed = True
        self.__stop__()

    def stop_callback(self, callback, arg):
        self.callback = callback
        self.thread_contral = arg

    def __stop__(self):
        if self.callback:
            self.callback(self.thread_contral, self)
