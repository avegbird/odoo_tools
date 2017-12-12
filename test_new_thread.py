# -*- coding: utf-8 -*-
import odoo_thread


class TextModel(models.Model):
    _name = 'text.model'
    _description = """用法示例 tips:可能会有错误，并没有运行测试。。"""

    text_char = fields.Char(string=u'测试用例', default=False)

    @staticmethod
    def task_to_do_background(self, **kwargs):
        # self.env['text.model']
        text = self.browse(kwargs['text_id'])
        text.text_char = u'测试'

    @staticmethod
    def over_callback(self, **kwargs):
        print u'成功'

    @staticmethod
    def failed_callback(self, **kwargs):
        if kwargs and '__exception' in kwargs:
            print kwargs['__exception']
            self = self.browse(kwargs['text_id'])
            self.text_char = kwargs['__exception'].name if 'name' in kwargs['__exception'] else u'未知错误'

    @api.multi
    def the_text_do(self):
        self.ensure_one()
        # 多个线程需要后台排队运行时，推荐
        my_thread = odoo_thread.Odoo_Thread(dbname=self._cr.dbname, table_name=self._name, user_id=self.env.user.id, retry_times=3,
                                            retry_delay=10, delay_time=4, over_callback=TextModel.over_callback,
                                            error_callback=TextModel.failed_callback)
        my_thread.thread_factory(name_target={str(i): (TextModel.task_to_do_background, {'text_id': i}, True)
                                              for i in range(10)})
        # 线程最大并发数，一般不适合超过10，4G内存电脑50个就会宕机
        my_thread._Max_Running_Threads = 3
        my_thread.start_all()

        # 只需要单个线程后台执行
        t1 = odoo_thread.Odoo_thread.new_thread(dbname=self._cr.dbname, table_name=self._name, user_id=self.env.user.id,
                                                retry_times=3, retry_delay=10, delay_time=4,
                                                target=TextModel.task_to_do_background, args={'text_id': 10})
        t1.setDaemon(True)
        t1.start()
