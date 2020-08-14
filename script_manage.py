import os
import builtins
import math
import codecs
import json
import shutil
import threading
import traceback
import time
import rm_define
import duss_event_msg
import duml_cmdset
import dji_scratch_project_parser
import rm_block_description
import rm_ctrl
import event_client
import tools
import builtins
import rm_log
import gc
import rm_builtins

logger = rm_log.dji_scratch_logger_get()

rm_func_names = {
    'RmList': rm_builtins.RmList,
    'rmround': rm_builtins.rmround,
    'rmexit':  rm_builtins.rmexit,
}

safe_func_names = [
    'None',
    'False',
    'True',
    'Exception',
    'abs',
    'all',
    'bool',
    'callable',
    'chr',
    'complex',
    'divmod',
    'dict',
    'float',
    'hash',
    'hex',
    'id',
    'int',
    'isinstance',
    'issubclass',
    'list',
    'len',
    'oct',
    'ord',
    'pow',
    'range',
    'repr',
    'round',
    'slice',
    'str',
    'tuple',
    'zip',
    'exit',
    'globals',
    'locals',
    'print',
    'min',  # Additional Function
    'max'
]

#need to add safe modules name
safe_module_names = [
    'event_client',
    'rm_ctrl',
    'rm_define',
    'rm_block_description',
    'rm_log',
    'tools',
    'time',
    'math',
    'random',
    'threading',
    'traceback',
    'tracemalloc',
    'socket', # from here I added some packages
    'sys',
    'subprocess',
    'contextlib'
]


def _hook_import(name, *args, **kwargs):
    if name in safe_module_names:
        return __import__(name, *args, **kwargs)
    else:
        raise RuntimeError('invalid module, the module is ' + str(name))
_builtins = {'__import__':_hook_import}

for name in safe_func_names:
    _builtins[name] = getattr(builtins, name)

for (name, item) in rm_func_names.items():
    _builtins[name] = item

_globals = {
    '__builtins__' : _builtins
}

_globals_exec = None

class ScriptCtrl(object):
    def __init__(self, event_client, script_path = '/data/script/file/'):
        self.event_client = event_client
        self.msg_buff = duss_event_msg.EventMsg(tools.hostid2senderid(event_client.my_host_id))
        self.msg_buff.set_default_receiver(rm_define.mobile_id)
        self.msg_buff.set_default_cmdset(duml_cmdset.DUSS_MB_CMDSET_RM)
        self.msg_buff.set_default_cmdtype(duml_cmdset.REQ_PKG_TYPE)

        self.scratch_python_code_line_offset = 0
        self.get_framework_data()

        self.script_file_list = []
        self.has_scripts_running = False
        self.run_script_id = '00000000000000000000000000000000'
        self.target_script = None
        self.scripts_running_thread_obj = None
        self.script_thread_mutex = threading.Lock()

        self.__dirc = script_path
        if not os.path.exists(self.__dirc):
            logger.warn('%s is not exist! create first'%(self.__dirc))
            os.makedirs(self.__dirc)

        self.file_prefix = 'dji_scratch_'
        self.lab_prefix = '_lab'
        self.custom_prefix = '_custom'
        self.python_suffix = '.py'
        self.dsp_suffix = '.dsp'

        # auto program
        self.custome_skill_running = False
        self.off_control_running = False
        self.custom_skill_config_dict = {}
        self.custom_skill_config_dict = self.read_custome_skill_dict()

        # block description state
        self.time_counter = 0
        self.sorted_variable_name_list = None
        self.variable_name_wait_push_list = []
        self.__block_description_dict_list = []
        self.__scratch_block_state = 'IDLE'
        self.__scratch_block_dict = {'id' : 'ABCDEFGHIJ0123456789', 'name' : 'IDLE', 'type' : 'INFO_PUSH'}
        self.__scratch_variable_push_flag = False
        self.__scratch_variable_push_name = ''

        #report traceback
        self.error_report_enable = True
        self.error_report_time = 0
        self.report_traceback_dict = {'script_id':0, 'traceback_msg':'', 'traceback_line':0, 'traceback_len':0, 'traceback_valid':0}
        self.report_traceback_dict_mutex = threading.Lock()

        self.block_description_mutex = threading.Lock()
        self.block_push_timer = tools.get_timer(0.02, self.scatch_script_block_push_timer)  # 50Hz
        self.block_push_timer.start()
        self.query()

        self.scheduler_param_high = os.sched_param(20)
        self.scheduler_param_middle = os.sched_param(15)
        self.scheduler_param_low = os.sched_param(5)

    def stop(self):
        logger.info('SCRIPT_CTRL: STOP')
        self.block_push_timer.join()
        self.block_push_timer.stop()
        self.block_push_timer.destory()

    def find_script_file_in_list(self, file_list, guid, suffix = '.py'):
        target_file = None
        file_suffix = guid + suffix
        for file in file_list:
            if file.endswith(file_suffix):
                target_file = file
                break
        return target_file

    def check_dsp_file(self, guid, sign):
        self.query()
        target_file = self.find_script_file_in_list(self.script_file_list, guid, self.dsp_suffix)
        if target_file == None:
            return duml_cmdset.DUSS_MB_RET_NO_EXIST_DSP

        dsp_str = self.read_script_string(os.path.join(self.__dirc, target_file))
        dsp_parser = dji_scratch_project_parser.DSPXMLParser()
        dsp_parser.parseDSPString(dsp_str)

        if 'sign' not in dsp_parser.dsp_dict.keys() or dsp_parser.dsp_dict['sign'] != sign:
            return duml_cmdset.DUSS_MB_RET_NO_EXIST_DSP

        return duml_cmdset.DUSS_MB_RET_OK

    def query(self):
        try:
            if not os.path.exists(self.__dirc):
                os.makedirs(self.__dirc)
            self.script_file_list = os.listdir(self.__dirc)
        except:
            logger.fatal(traceback.format_exc())

    def scratch_python_code_line_offset_get(self, framework_data):
        script_data_list = framework_data.splitlines()
        try:
            self.scratch_python_code_line_offset = script_data_list.index('SCRATCH_PYTHON_CODE')
            logger.info('user python code offset is %d' %self.scratch_python_code_line_offset)
        except:
            logger.error('GET SCRATCH_PYTHON_CODE OFFSET ERROR')
            self.scratch_python_code_line_offset = 0

    def get_framework_data(self):
        try:
            framework_fd = codecs.open('/data/dji_scratch/framework/script_framework.py', 'r', encoding = 'utf-8')
            self.framework_data = framework_fd.read()
            self.scratch_python_code_line_offset_get(self.framework_data)
            framework_fd.close()
            custom_skill_framework_fd = codecs.open('/data/dji_scratch/framework/custom_skill_framework.py', 'r', encoding = 'utf-8')
            self.custome_skill_framework_data = custom_skill_framework_fd.read()
            custom_skill_framework_fd.close()
        except:
            logger.fatal('SCRIPT_CTRL: No framework code file, please make sure the \'framework.py\' exits')

    def read_script_string(self, file_name):
        try:
            fd = codecs.open(file_name, 'r', encoding = 'utf-8')
            str = fd.read()
            fd.close()
            return str
        except:
            logger.fatal(traceback.format_exc())

    def write_script_string(self, file_name, buffer):
        try:
            script_fd = codecs.open(file_name, 'w', encoding = 'utf-8')
            script_fd.write(buffer)
            script_fd.close()
        except:
            logger.fatal(traceback.format_exc())

    def reset_states(self):
        self.script_thread_mutex.acquire()
        self.has_scripts_running = False
        self.run_script_id = '00000000000000000000000000000000'
        self.target_script = None
        self.scripts_running_thread_obj = None
        self.custome_skill_running = False
        self.off_control_running = False
        self.script_thread_mutex.release()

    def set_states(self, running, script_id, target_script, thread_obj, custom, off_control):
        self.script_thread_mutex.acquire()
        self.has_scripts_running = running
        self.run_script_id = script_id
        self.target_script = target_script
        self.scripts_running_thread_obj = thread_obj
        self.custome_skill_running = custom
        self.off_control_running = off_control
        self.script_thread_mutex.release()

    def start_running(self, script_id, custome_id):
        self.query()
        if self.has_scripts_running:
            logger.warn('SCRIPT_CTRL: has script running')
            return rm_define.DUSS_ERR_BUSY

        if custome_id != None:
            if not custome_id in self.custom_skill_config_dict.keys():
                logger.warn('SCRIPT_CTRL: auto program is not configured')
                return rm_define.DUSS_ERR_FAILURE
            script_id = self.custom_skill_config_dict[custome_id]
            file_suffix = self.custom_prefix + self.python_suffix
            if int(custome_id) >= 0 and int(custome_id) <= 9:
                logger.info('SCRIPT_CTRL: custome skill start!')
                custom_skill_flag, off_control_flag = True, False
            else:
                logger.info('SCRIPT_CTRL: off control start!')
                custom_skill_flag, off_control_flag = False, True
        else:
            file_suffix = self.lab_prefix + self.python_suffix
            custom_skill_flag, off_control_flag = False, False

        # find script file
        target_script = self.find_script_file_in_list(self.script_file_list, script_id, file_suffix)

        if target_script != None:
            self.set_states(True, script_id, target_script, None, custom_skill_flag, off_control_flag)
            script_thread_obj = threading.Thread(target=self.execute_thread)
            self.set_states(True, script_id, target_script, script_thread_obj, custom_skill_flag, off_control_flag)
            script_thread_obj.start()
            return rm_define.DUSS_SUCCESS
        else:
            logger.error('SCRIPT_CTRL: can not find script id = ' + str(script_id))
            return rm_define.DUSS_ERR_FAILURE

    def stop_running(self, script_id, custome_id):
        if custome_id != None:
            if not custome_id in self.custom_skill_config_dict.keys():
                logger.error('SCRIPT_CTRL: custome skill is not configured')
                return rm_define.DUSS_ERR_FAILURE
            script_id = self.custom_skill_config_dict[custome_id]
            file_suffix = self.custom_prefix + self.python_suffix
        else:
            file_suffix = self.lab_prefix + self.python_suffix
        # check the exit script
        file_suffix = script_id + file_suffix
        if self.has_scripts_running == False or self.target_script == None or not self.target_script.endswith(file_suffix):
            logger.warn('SCRIPT_CTRL: no request script running!')
            return rm_define.DUSS_ERR_FAILURE

        try:
            global _globals_exec
            if isinstance(_globals_exec, dict) and 'event' in _globals_exec.keys() and _globals_exec['event'].script_state.check_script_has_stopped() == False:
                _globals_exec['event'].script_state.set_stop_flag()
                self.error_report_enable = False
            else:
                logger.warn('SCRIPT_CTRL: script are going to finish!')
                return rm_define.DUSS_SUCCESS
        except Exception as e:
            logger.fatal(traceback.format_exc())

        logger.info('\n**************** script exit successful ****************')
        return rm_define.DUSS_SUCCESS

    def reset_whole_script_state(self):
        self.reset_states()
        self.reset_block_state_pusher()

    def execute_thread(self):
        os.sched_setscheduler(0, os.SCHED_RR, self.scheduler_param_low)
        script_file_name = self.__dirc + self.target_script
        self.clear_report_traceback_msg()
        _error_msg = ''
        try:
            _globals['block_description_push'] = self.push_block_description_info_to_timer
            _globals['_error_msg'] = ''

            global _globals_exec
            _globals_exec = dict(_globals)

            script_str = self.read_script_string(script_file_name)

            # run custome skill
            if self.custome_skill_running:
                self.set_block_to_CUSTOME_SKILL()
            elif self.off_control_running:
                _globals_exec['speed_limit_mode'] = True
                self.set_block_to_OFF_CONTROL()
            else:
                self.set_block_to_RUN()

            logger.fatal('**************** script start successful ****************')
            logger.fatal('MANAGER: EXEC filename = ' + script_file_name)
            logger.fatal('MANAGER: EXEC code: ')
            logger.info(script_str)

            lt = time.time()
            exec(script_str, _globals_exec)
        except Exception as e:
            logger.fatal(traceback.format_exc())
            _error_msg = traceback.format_exc()
        finally:
            if _error_msg == '':
                _error_msg = _globals_exec['_error_msg']

            if self.error_report_enable:
                self.block_description_mutex.acquire()
                block_id = self.__scratch_block_dict['id']
                if len(self.__block_description_dict_list) != 0:
                    block_id = self.__block_description_dict_list[-1]['id']
                self.block_description_mutex.release()

                self.update_report_traceback_msg(self.run_script_id, block_id, _error_msg)
            else:
                logger.info('Not report traceback msg')
                self.error_report_enable = True

            if isinstance(_globals_exec, dict) and 'event' in _globals_exec.keys():
                _globals_exec['event'].stop()
                del _globals_exec['event']

            # wait variable push finsh, make sure all variable be update, timeout=3s
            timeout_count = 0
            while len(self.variable_name_wait_push_list) != 0 and timeout_count < 150:
                timeout_count += 1
                time.sleep(0.02)

            ct = time.time()

            #hack code, block state timer push freq is 50Hz
            if ct - lt < 0.1:
                logger.info('exec too fast, wait 0.1s to make sure block state to be updated successfully')
                time.sleep(0.1)

            self.reset_whole_script_state()
            _globals_exec = None
            gc.collect()
            logger.fatal('\n**************** script finsh successful ****************')

    def get_script_data(self, buffer):
        duss_result = duml_cmdset.DUSS_MB_RET_FINSH
        try:
            dsp_parser = dji_scratch_project_parser.DSPXMLParser()
            dsp_res = dsp_parser.parseDSPString(buffer)
            if dsp_res == -1:
                logger.error('SCRIPT_CTRL: dsp file MD5 check failure')
                return duml_cmdset.DUSS_MB_RET_MD5_CHECK_FAILUE, None, None, None, None
            if dsp_res == -2:
                logger.error('SCRIPT_CTRL: dsp file parse failure')
                logger.error(buffer)
                return rm_define.DUSS_ERR_FAILURE, None, None, None, None
            script_data = dsp_parser.dsp_dict['python_code']
            guid = dsp_parser.dsp_dict['guid']
            sign = dsp_parser.dsp_dict['sign']
            code_type = dsp_parser.dsp_dict['code_type']
            return duss_result, script_data, guid, sign, code_type
        except:
            logger.fatal(traceback.format_exc())

    def script_add_indent(self, script_data):
        script_data_list = script_data.splitlines()
        script_data = ''
        for script_oneline in script_data_list:
            script_data = script_data + '    ' +script_oneline + '\n'
        return script_data

    def parse_descriptions(self, script_data):
        script_data_list = script_data.splitlines()
        script_data = ''
        for script_oneline in script_data_list:
            if script_oneline.find('#') != -1:
                s_list = script_oneline.split('#', 1)
                t_dict, res = rm_block_description.parse_oneline_block_description('#' + s_list[1])
                if 'block' in t_dict.keys():
                    script_oneline = s_list[0] + 'block_description_push(' + s_list[1][len('block '):].replace(' ', ', ') + ')'
            script_data = script_data +script_oneline + '\n'
        return script_data

    def script_add_check_point(self, script_data):
        script_data_list = script_data.splitlines()
        script_data = ''
        for script_oneline in script_data_list:
            if ('#' not in script_oneline) and ('while ' in script_oneline or 'while(' in script_oneline or ('for ' in script_oneline and ' in ' in script_oneline and ':' in script_oneline)):
                space_num = 0
                if 'while ' in script_oneline:
                    space_num = script_oneline.find('while ')
                if 'while(' in script_oneline:
                    space_num = script_oneline.find('while(')
                elif ('for ' in script_oneline and ' in ' in script_oneline and ':' in script_oneline):
                    space_num = script_oneline.find('for')
                space_str = (4+space_num) * ' '
                add_str = '\n' + space_str + 'time.sleep(0.005)'
                script_oneline += add_str
            script_data = script_data + script_oneline + '\n'
        return script_data

    def create_file(self, data):
        if not self.has_scripts_running:
            self.set_block_to_START()
        duss_result = duml_cmdset.DUSS_MB_RET_FINSH
        self.query()

        dsp_buffer_byte = tools.pack_to_byte(data)
        dsp_buffer = dsp_buffer_byte.decode('utf-8')
        duss_result, script_data, file_guid, sign, code_type = self.get_script_data(dsp_buffer)
        if duss_result != duml_cmdset.DUSS_MB_RET_FINSH:
            return duss_result

        script_data = self.script_add_check_point(script_data)
        script_data = self.script_add_indent(script_data)

        custom_script_data = script_data
        lab_script_data = script_data

        if code_type == 'scratch' or code_type == '':
            logger.info('SCRIPT_CTRL: cur code type is scratch')
            lab_script_data = self.parse_descriptions(script_data)
        elif code_type == 'python':
            logger.info('SCRIPT_CTRL: cur code type is python')
            pass #do nothing

        lab_script_data = self.framework_data.replace('SCRATCH_PYTHON_CODE', lab_script_data)
        custom_script_data = self.custome_skill_framework_data.replace('SCRATCH_PYTHON_CODE', custom_script_data)

        # remove same 'guid' old files
        try:
            for file in self.script_file_list:
                if not os.path.isdir(os.path.join(self.__dirc, file)) and file.find(file_guid) != -1:
                    os.remove(os.path.join(self.__dirc, file))
                    logger.info('SCRIPT_CTRL: remove file: ' + file)
        except:
            logger.fatal(traceback.format_exc())

        python_file_name = self.file_prefix + time.strftime("%Y%m%d%H%M%S_") + file_guid

        lab_script_name = python_file_name + self.lab_prefix + self.python_suffix
        save_lab_script_name = os.path.join(self.__dirc, lab_script_name)
        self.write_script_string(save_lab_script_name, lab_script_data)

        custom_script_name = python_file_name + self.custom_prefix + self.python_suffix
        save_custom_script_name = os.path.join(self.__dirc, custom_script_name)
        self.write_script_string(save_custom_script_name, custom_script_data)

        logger.info('SCRIPT_CTRL: create python file: %s(_custom/_lab).py'%python_file_name)

        dsp_file_name = self.file_prefix + time.strftime("%Y%m%d%H%M%S_") + file_guid + self.dsp_suffix
        save_dsp_file_name = os.path.join(self.__dirc, dsp_file_name)
        logger.info('SCRIPT_CTRL: create dsp file: ' + dsp_file_name)
        self.write_script_string(save_dsp_file_name, dsp_buffer)

        if not self.has_scripts_running:
            self.set_block_to_IDLE()

        self.query()
        return duss_result

    def delete_file(self, guid, sign):
        self.query()
        target_file = self.find_script_file_in_list(self.script_file_list, guid, self.dsp_suffix)
        if target_file == None:
            return rm_define.DUSS_ERR_FAILURE

        dsp_str = self.read_script_string(os.path.join(self.__dirc, target_file))
        dsp_parser = dji_scratch_project_parser.DSPXMLParser()
        dsp_parser.parseDSPString(dsp_str)
        if dsp_parser.dsp_dict['sign'] == sign:
            os.remove(os.path.join(self.__dirc, target_file))
            os.remove(os.path.join(self.__dirc, target_file.replace(self.dsp_suffix, self.lab_prefix + self.python_suffix)))
            os.remove(os.path.join(self.__dirc, target_file.replace(self.dsp_suffix, self.custom_prefix + self.python_suffix)))
            return rm_define.DUSS_SUCCESS
        else:
            return rm_define.DUSS_ERR_FAILURE

    def delete_all_file(self):
        duss_result = rm_define.DUSS_SUCCESS
        try:
            shutil.rmtree(self.__dirc)
            os.mkdir(self.__dirc)
        except:
            logger.warn('SCRIPT_CTRL: delete all file failure')
            duss_result = rm_define.DUSS_ERR_FAILURE
        self.query()
        return duss_result

    def load_custome_skill(self, custome_id, guid, sign):
        if self.has_scripts_running:
            return rm_define.DUSS_ERR_FAILURE
        self.query()
        target_file = self.find_script_file_in_list(self.script_file_list, guid, self.dsp_suffix)
        if target_file == None:
            return rm_define.DUSS_ERR_FAILURE
        dsp_str = self.read_script_string(os.path.join(self.__dirc, target_file))
        dsp_parser = dji_scratch_project_parser.DSPXMLParser()
        dsp_parser.parseDSPString(dsp_str)
        if dsp_parser.dsp_dict['sign'] != sign:
            return rm_define.DUSS_ERR_FAILURE
        self.custom_skill_config_dict[custome_id] = guid
        self.save_custome_skill_dict(self.custom_skill_config_dict)
        return rm_define.DUSS_SUCCESS

    def unload_custome_skill(self, custome_id):
        if self.has_scripts_running:
            return rm_define.DUSS_ERR_FAILURE
        if custome_id in self.custom_skill_config_dict.keys():
            self.custom_skill_config_dict.pop(custome_id)
            self.save_custome_skill_dict(self.custom_skill_config_dict)
        return rm_define.DUSS_SUCCESS

    def query_custome_skill(self, custome_id):
        # check custome_id is configured
        if not custome_id in self.custom_skill_config_dict.keys():
            return rm_define.DUSS_ERR_FAILURE, None, None
        query_guid = self.custom_skill_config_dict[custome_id]
        self.query()
        # check dsp is exist
        target_file = self.find_script_file_in_list(self.script_file_list, query_guid, self.dsp_suffix)
        if target_file == None:
            return rm_define.DUSS_ERR_FAILURE, None, None
        dsp_str = self.read_script_string(os.path.join(self.__dirc, target_file))
        dsp_parser = dji_scratch_project_parser.DSPXMLParser()
        dsp_parser.parseDSPString(dsp_str)
        query_sign = dsp_parser.dsp_dict['sign']
        logger.info('SCRIPT_CTRL: query success, guid:%s, sign:%s' %(query_guid, query_sign))
        return rm_define.DUSS_SUCCESS, query_guid, query_sign

    def save_custome_skill_dict(self, t_dict, file_name = 'custom_skill_config.json'):
        file_name = os.path.join(self.__dirc, file_name)
        config_file = open(file_name, 'w')
        json.dump(t_dict, config_file, ensure_ascii = True)

    def read_custome_skill_dict(self, file_name = 'custom_skill_config.json'):
        t_dict = {}
        file_name = os.path.join(self.__dirc, file_name)
        try:
            config_file = open(file_name, 'r')
            json_str = config_file.read()
            t_dict = json.loads(json_str)
        except Exception as e:
            self.save_custome_skill_dict(t_dict)
            logger.error('SCRIPT_CTRL: error! message: ')
            logger.error('TRACEBACK:\n' + traceback.format_exc())
        return t_dict

    def update_scratch_block_state(self, block_dict):
        self.__scratch_block_state = block_dict['name']
        if block_dict['name'] != 'IDLE' and block_dict['name'] != 'SCRIPT_START' and block_dict['name'] != 'CUSTOME_SKILL' and block_dict['name'] != 'OFF_CONTROL':
            self.__scratch_block_state = 'SCRIPT_RUN'

    def scatch_script_block_push_timer(self, *arg, **kw):
        state_switch_flag = 'NO_CHANGE'
        if len(self.__block_description_dict_list) > 0:
            self.block_description_mutex.acquire()
            block_dict = self.__block_description_dict_list.pop(0)
            self.block_description_mutex.release()
            # check 'id' difference
            if self.__scratch_block_dict['id'] != block_dict['id'] or 'data_' in block_dict['name']:
                state_switch_flag = 'CHANGED'
                # check the 'running_state' in last block
                if 'running_state' in self.__scratch_block_dict.keys() and 'running_state' in block_dict.keys():
                    self.__scratch_block_dict['running_state'] = block_dict['running_state']
                    block_dict['running_state'] = rm_define.BLOCK_RUN_SUCCESS
                    self.state_pusher_send_msgbuf(state_switch_flag)
                #update the current block state
                self.__scratch_block_dict = block_dict
                self.update_scratch_block_state(block_dict)
                logger.debug('BLOCK: state change to: ' + self.__scratch_block_state + ', block ID: ' + block_dict['id'])

        self.state_pusher_send_msgbuf(state_switch_flag)

    def set_block_to_CUSTOME_SKILL(self):
        self.push_block_description_info_to_timer(id="ABCDEFGHIJ1234567899", name="CUSTOME_SKILL", type="INFO_PUSH")

    def set_block_to_OFF_CONTROL(self):
        self.push_block_description_info_to_timer(id="ABCDEFGHIJ1234567898", name="OFF_CONTROL", type="INFO_PUSH")

    def set_block_to_IDLE(self):
        self.push_block_description_info_to_timer(id="ABCDEFGHIJ1234567897", name="IDLE", type="INFO_PUSH")

    def set_block_to_START(self):
        self.push_block_description_info_to_timer(id="ABCDEFGHIJ1234567896", name="SCRIPT_START", type="INFO_PUSH")

    def set_block_to_RUN(self):
        #no block_description info, just change state
        self.push_block_description_info_to_timer(id="ABCDEFGHIJ1234567895", name="SCRIPT_RUN", type="INFO_PUSH")

    def get_sorted_variable_name_list(self):
        global _globals_exec
        self.sorted_variable_name_list = []
        if isinstance(_globals_exec, dict):
            for (k, v) in _globals_exec.items():
                if isinstance(k, str) and k.startswith('variable_') or k.startswith('list_') :
                    self.sorted_variable_name_list.append(k)
            self.sorted_variable_name_list = sorted(self.sorted_variable_name_list)

        logger.info('BLOCK: sorted variable is %s' %(str(self.sorted_variable_name_list)))

    def get_target_variable_index_and_value(self, var_name):
        global _globals_exec
        if self.sorted_variable_name_list == None:
            return None, None
        if var_name != '' and var_name in _globals_exec.keys() and var_name in self.sorted_variable_name_list:
            index = self.sorted_variable_name_list.index(var_name)
            value = _globals_exec[var_name]
            return index, value
        else:
            return None, None

    def get_block_running_state(self):
        running_state = None
        global _globals_exec
        if isinstance(_globals_exec, dict) and 'event' in _globals_exec.keys():
            running_state = _globals_exec['event'].script_state.get_block_running_state()
        return running_state

    def get_block_running_percent(self):
        percent = 100
        global _globals_exec
        if isinstance(_globals_exec, dict) and 'event' in _globals_exec.keys():
            percent = _globals_exec['event'].script_state.get_block_running_percent()
        return percent

    def push_block_description_info_to_timer(self, **src_block_dict):
        global _globals_exec
        block_running_state = self.get_block_running_state()
        # check the script is needed to stop or not

        if isinstance(_globals_exec, dict) and 'tools' in _globals_exec.keys():
            _globals_exec['tools'].wait(0)

        block_dict = src_block_dict
        # check dict have 'id' and 'name' item
        if 'id' not in block_dict.keys() or 'name' not in block_dict.keys():
            return
        if 'name' in block_dict.keys() and block_dict['name'] == 'robot_on_start':
            self.get_sorted_variable_name_list()

        #extract var
        push_variable = ''
        if 'curvar' in block_dict.keys():
            if self.__scratch_variable_push_flag:
                self.__scratch_variable_push_flag = False
                if self.__scratch_variable_push_name not in self.variable_name_wait_push_list:
                    self.variable_name_wait_push_list.append(self.__scratch_variable_push_name)
            if block_dict['curvar'] != '':
                self.__scratch_variable_push_flag = True
                self.__scratch_variable_push_name = block_dict['curvar']
        if block_running_state != None:
            block_dict['running_state'] = block_running_state

        # insert dict to list
        self.block_description_mutex.acquire()
        self.__block_description_dict_list.append(block_dict)
        self.block_description_mutex.release()

    # 0xA5
    def state_pusher_send_msgbuf(self, push_flag):
        self.time_counter = self.time_counter + 1
        #push in to mobile changeless freq
#        push_flag = 'NO_CHANGED'
        if push_flag == 'CHANGED' or self.time_counter == 10: #5Hz
            self.time_counter = 0
            block_state_table = {'IDLE' : 0, 'SCRIPT_START' : 1, 'SCRIPT_RUN' : 2, 'CUSTOME_SKILL' : 3, 'OFF_CONTROL' : 4, 'ERROR' : 5}
            block_type_table = {'SET_PROPERTY' : 0, 'CONTINUE_CONTROL' : 1, 'TASK' : 2, 'RESPONSE_NOW' : 3, 'INFO_PUSH' : 4, 'EVENT' : 5, 'CONDITION_WAIT' : 6}

            self.msg_buff.init()
            percent = self.get_block_running_percent()
            block_running_state = rm_define.BLOCK_RUN_SUCCESS
            if 'running_state' in self.__scratch_block_dict.keys():
                block_running_state = self.__scratch_block_dict['running_state']

            self.msg_buff.append('script_state', 'uint8', block_state_table[self.__scratch_block_state])
            self.msg_buff.append('script_id', 'bytes', tools.string_to_byte(self.run_script_id))
            self.msg_buff.append('block_id_len', 'uint8', 20)
            self.msg_buff.append('block_id', 'bytes', tools.string_to_byte(self.__scratch_block_dict['id']))
            self.msg_buff.append('exec_result', 'uint8', block_running_state)
            self.msg_buff.append('block_type', 'uint8', 0)
            self.msg_buff.append('exec_precent', 'uint8', percent)

            if len(self.variable_name_wait_push_list) != 0:
                var_name = self.variable_name_wait_push_list.pop(0)
                self.msg_buff.append('variable_len', 'uint16', 1)
                index, value = self.get_target_variable_index_and_value(var_name)
                if isinstance(value, rm_builtins.RmList) or isinstance(value, list):
                    offset = 0
                    if isinstance(value, rm_builtins.RmList):
                        offset = 1
                    if len(value) == 0:
                        idx = 2 << 14 | index << 7 #empty list
                        self.msg_buff.append('variable_len', 'uint16', 1)
                        self.msg_buff.append('var' + str(idx), 'uint16', idx)
                        self.msg_buff.append('var_value' + str(idx), 'float', 0)
                    else:
                        self.msg_buff.append('variable_len', 'uint16', len(value))
                        for index_t in range(len(value) + offset)[offset:]:
                            if index_t >= 0x80:
                                self.msg_buff.append('variable_len', 'uint16', 0x80)
                                break
                            idx = 1 << 14 | index << 7 | index_t # list 15:14 | list_var_index 13:7 | list_elem_index 6:0
                            self.msg_buff.append('var' + str(idx), 'uint16', idx)
                            self.msg_buff.append('var_value' + str(idx), 'float', value[index_t])
                elif index != None:
                    index &= 0x7f
                    self.msg_buff.append('var' + str(index), 'uint16', index)
                    self.msg_buff.append('var_value' + str(index), 'float', float(value))
            else:
                self.msg_buff.append('variable_len', 'uint16', 0)

            self.msg_buff.cmd_id = duml_cmdset.DUSS_MB_CMD_RM_SCRIPT_BLOCK_STATUS_PUSH
            self.msg_buff.receiver = rm_define.hdvt_uav_id

            duss_result = self.event_client.send_msg(self.msg_buff)

            if self.__scratch_block_state == 'IDLE':
                self.report_traceback_dict_mutex.acquire()
                if self.report_traceback_dict['traceback_valid'] != 0 and self.error_report_time < 3:
                    self.error_report_time = self.error_report_time + 1
                    #errror report
                    logger.info('Report error %d th', self.error_report_time)
                    self.msg_buff.init()
                    self.msg_buff.append('script_state', 'uint8', block_state_table['ERROR'])
                    self.msg_buff.append('script_id', 'string', self.report_traceback_dict['script_id'])
                    self.msg_buff.append('traceback_valid', 'uint8', self.report_traceback_dict['traceback_valid'])
                    self.msg_buff.append('block_id_len', 'uint8', 20)
                    self.msg_buff.append('block_id', 'string', self.report_traceback_dict['block_id'])
                    self.msg_buff.append('err_code', 'uint8', tools.get_fatal_code(self.report_traceback_dict['traceback_msg']))
                    self.msg_buff.append('reserved', 'string', '\x00'*2) #need to align
                    self.msg_buff.append('traceback_line', 'uint32', self.report_traceback_dict['traceback_line'])
                    self.msg_buff.append('traceback_len', 'uint16', self.report_traceback_dict['traceback_len'])
                    self.msg_buff.append('traceback_msg', 'string', self.report_traceback_dict['traceback_msg'])
                    self.report_traceback_dict_mutex.release()
                elif self.error_report_time > 0: #at least once
                    self.report_traceback_dict_mutex.release()
                    self.clear_report_traceback_msg()
                    self.error_report_time = 0
                else:
                    self.report_traceback_dict_mutex.release()

            self.msg_buff.receiver = rm_define.mobile_id
            duss_result = self.event_client.send_msg(self.msg_buff)


    def reset_block_state_pusher(self):
        self.block_description_mutex.acquire()
        self.__block_description_dict_list = []
        self.block_description_mutex.release()
        self.sorted_variable_name_list = None
        self.set_block_to_IDLE()
        global _globals_exec
        _globals_exec = None
        logger.info('BLOCK: reset, state change to IDLE')

    def update_report_traceback_msg(self, script_id, block_id, traceback_msg):
        self.report_traceback_dict_mutex.acquire()
        self.report_traceback_dict['script_id'] = script_id
        self.report_traceback_dict['block_id'] = block_id
        line = 0
        if len(traceback_msg) == 0:
            self.report_traceback_dict['traceback_valid'] = 0
        else:
            traceback_msg = traceback_msg.splitlines()

            error_type=traceback_msg[-1]
            traceback_msg_str = ''
            break_flag=False

            ## handle diff error type msg
            ## - Exception and Name error msg -- no error position
            ## - SyntaxError and IndentationError error msg -- parse error position
            if 'Exception:' in error_type or 'NameError:' in error_type:
                for msg in traceback_msg:
                    if 'File "<string>"' in msg:
                        traceback_msg_str = msg + '\n'
                    else:
                        if traceback_msg_str:
                            break
            else:
                for msg in traceback_msg:
                    if break_flag:
                        ## may error position, record
                        traceback_msg_str += msg + '\n'
                        break
                    if 'File "<string>"' in msg:
                        traceback_msg_str = msg + '\n'
                    else:
                        if traceback_msg_str:
                            traceback_msg_str += msg + '\n'
                            break_flag=True
                            continue
            traceback_msg_str =  traceback_msg[0] + '\n' + traceback_msg_str + traceback_msg[-1] + '\n'
            traceback_msg = traceback_msg_str

            ## recalc error line
            line_pos = traceback_msg.rfind('line')
            line_str = traceback_msg[line_pos+len('line '):]
            try:
                line = int(line_str[0:line_str.find('\n')])
            except:
                try:
                    line = int(line_str[0:line_str.find(',')])
                except:
                    line = 0
            if line >= self.scratch_python_code_line_offset:
                new_line = line - self.scratch_python_code_line_offset
            else:
                new_line = 0

            #TODO: should check line only one
            traceback_msg = traceback_msg.replace('line ' + str(line), 'line ' + str(new_line))
            traceback_msg = traceback_msg.replace('<string>', '<CurFile>')
            traceback_msg = traceback_msg.replace('<module>', '<CurModule>')
            line = new_line
            self.report_traceback_dict['traceback_valid'] = 1
            self.report_traceback_dict['traceback_line'] = line
            self.report_traceback_dict['traceback_len'] = len(traceback_msg)
            self.report_traceback_dict['traceback_msg'] = traceback_msg
        self.report_traceback_dict_mutex.release()

    def clear_report_traceback_msg(self):
        self.report_traceback_dict_mutex.acquire()
        self.report_traceback_dict['script_id'] = ''
        self.report_traceback_dict['block_id'] = ''
        self.report_traceback_dict['traceback_valid'] = 0
        self.report_traceback_dict['traceback_line'] = 0
        self.report_traceback_dict['traceback_len'] = 0
        self.report_traceback_dict['traceback_msg'] = ''
        self.report_traceback_dict_mutex.release()

    def get_report_traceback_msg(self):
        return dict(self.report_traceback_dict)

class ScriptProcessCtrl(object):
    def __init__(self, script_ctrl,local_sub_service):
        self.script_ctrl = script_ctrl
        self.local_sub_service = local_sub_service
        self.retry = 0
        self.script_raw_data = {}
        self.cmd_dict = {
                        1 : 'QUERY', 2 : 'RUN', 5 : 'EXIT', 6 : 'DELETE', 7 : 'DEL_ALL', 8 : 'CUSTOME_LOAD',
                        9 : 'CUSTOME_UNLOAD', 10 : 'CUSTOME_QUERY', 11 : 'CUSTOME_RUN', 12 : 'CUSTOME_EXIT'
                        }
    #0xA1
    def request_recv_script_file(self, event_client, msg):
        logger.info('REQUEST_CTRL: receive cmd 0xA1')
        buff = msg['data']
        if len(buff) < 4:
            logger.error('REQUEST_CTRL: data length is less than 4!')
            return

        seq_num = buff[1]
        length = (buff[3] << 8) | buff[2]
        if length != (len(buff)-4):
            logger.error('REQUEST_CTRL: data length check failure!')
            return
        data = buff[4: length+4]
        self.script_raw_data[seq_num] = data

    #0xA2
    def request_create_script_file(self, event_client, msg):
        logger.info('REQUEST_CTRL: receive cmd 0xA2')

        buff = msg['data']
        if len(buff) < 2:
            logger.error('REQUEST_CTRL: data length is less than 2!')
            event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_DOWNLOAD_FAILUE)
            return
        # check the sequences
        resend_seq_list = []
        seq_num = buff[1]
        if self.script_raw_data == {}:
            logger.info('REQUEST_CTRL:raw_data is {}, not need resend')
            return
        for seq in range(seq_num+1):
            if seq not in self.script_raw_data.keys():
                resend_seq_list.append(seq)
        # if not empty, resend
        if resend_seq_list:
            logger.info('REQUEST_CTRL: resend package sequences: ' + str(resend_seq_list))
            logger.info('REQUEST_CTRL: sequences max: ' + str(seq_num))
            if self.retry >= 5:
                logger.error('REQUEST_CTRL: retry achieve the max, send failure code to APP')
                self.reset_states()
                event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_DOWNLOAD_FAILUE)
            else:
                self.retry = self.retry + 1

                event_msg = duss_event_msg.unpack2EventMsg(msg)
                event_msg.clear()
                event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_RESEND_REQUEST)
                event_msg.append('resend_len', 'uint8', len(resend_seq_list))
                event_msg.append('data', 'bytes', resend_seq_list)
                event_client.resp_event_msg(event_msg)
            return

        logger.info('REQUEST_CTRL: sequence check success!')
        #flat the script_raw_data
        file_data = []
        for seq in range(seq_num+1):
            file_data.extend(self.script_raw_data[seq])

        # check MD5
        MD5 = buff[2:18]
        if not tools.md5_check(file_data, MD5):
            logger.error('REQUEST_CTRL: MD5 check failure')
            if self.retry >= 5:
                logger.error('REQUEST_CTRL: retry achieve the max, send failure code to APP')
                self.reset_states()
                event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_DOWNLOAD_FAILUE)
            else:
                self.retry = self.retry + 1
                event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_MD5_CHECK_FAILUE)
            return
        logger.info('REQUEST_CTRL: MD5 check success!')

        # creating script file
        duss_result = self.script_ctrl.create_file(file_data)
        self.reset_states()
        logger.info('REQUEST_CTRL: file create success!')

        event_client.resp_retcode(msg, duss_result)

    # 0xA3
    def request_ctrl_script_file(self, event_client, msg):
        logger.info('REQUEST_CTRL: receive cmd 0xA3')

        buff = msg['data']
        if len(buff) < 1:
            logger.error('REQUEST_CTRL: data length is less than 1!')
            event_client.resp_retcode(msg, rm_define.DUSS_ERR_FAILURE)
            return

        # check the supported CMD
        if (buff[0] & 0x0F) not in self.cmd_dict.keys():
            logger.info('REQUEST_CTRL: unsupported CMD: ' + str(buff[0] & 0x0F))
            event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_INVALID_CMD)
            return

        cmd = self.cmd_dict[buff[0] & 0x0F]
        custome_id = str((buff[0] & 0xF0) >> 4)

        if cmd != 'DEL_ALL' and cmd != 'CUSTOME_QUERY' and cmd != 'CUSTOME_RUN' and cmd != 'CUSTOME_EXIT' and cmd != 'CUSTOME_UNLOAD':
            if len(buff) < 49:
                logger.error('REQUEST_CTRL: cmd = %s, data length %d is less than 49!' %s (cmd, len(buff)))
                event_client.resp_retcode(msg, rm_define.DUSS_ERR_FAILURE)
                return
            guid_byte = tools.pack_to_byte(buff[1:33])
            sign_byte = tools.pack_to_byte(buff[33:49])

            guid = guid_byte.decode('utf-8')
            sign = sign_byte.decode('utf-8')

        if cmd == 'QUERY':
            logger.info('REQUEST_CTRL: query script file: ' + str(guid) + ' sign: ' + str(sign))
            duss_result = self.script_ctrl.check_dsp_file(guid, sign)
        elif cmd == 'RUN':
            logger.info('REQUEST_CTRL: start running script file: ' + str(guid) + ' sign: ' + str(sign))
            duss_result = self.script_ctrl.start_running(guid, None)
        elif cmd == 'EXIT':
            logger.info('REQUEST_CTRL: exiting the running script file: ' + str(guid) + ' sign: ' + str(sign))
            duss_result = self.script_ctrl.stop_running(guid, None)
        elif cmd == 'DELETE':
            logger.info('REQUEST_CTRL: request delete script file: ' + str(guid) + ' sign: ' + str(sign))
            duss_result = self.script_ctrl.delete_file(guid, sign)
        elif cmd == 'DEL_ALL':
            logger.info('REQUEST_CTRL: request delete ALL script file')
            duss_result = self.script_ctrl.delete_all_file()
        elif cmd == 'CUSTOME_LOAD':
            logger.info('REQUEST_CTRL: load custome skill script, index: %s, guid: %s'%(custome_id, guid))
            duss_result = self.script_ctrl.load_custome_skill(custome_id, guid, sign)
            logger.info('REQUEST_CTRL: current custome skill:')
            logger.info(self.script_ctrl.custom_skill_config_dict)
        elif cmd == 'CUSTOME_UNLOAD':
            logger.info('REQUEST_CTRL: unload custome skill script, index: %s'%(custome_id))
            duss_result = self.script_ctrl.unload_custome_skill(custome_id)
            logger.info('REQUEST_CTRL: current custome skill:')
            logger.info(self.script_ctrl.custom_skill_config_dict)
        elif cmd == 'CUSTOME_QUERY':
            logger.info('REQUEST_CTRL: query custome script, index: ' + custome_id)
            duss_result, guid, sign = self.script_ctrl.query_custome_skill(custome_id)
            if duss_result == rm_define.DUSS_SUCCESS:
                event_msg = duss_event_msg.unpack2EventMsg(msg)
                event_msg.clear()
                event_msg.append('ret_code', 'uint8', duss_result)
                event_msg.append('guid', 'bytes', tools.string_to_byte(guid))
                event_msg.append('sign', 'bytes', tools.string_to_byte(sign))
                event_client.resp_event_msg(event_msg)
                return
        elif cmd == 'CUSTOME_RUN':
            logger.info('REQUEST_CTRL: run custome script, index: ' + custome_id)
            duss_result = self.script_ctrl.start_running(None, custome_id)
        elif cmd == 'CUSTOME_EXIT':
            logger.info('REQUEST_CTRL: exit custome script, index: ' + custome_id)
            duss_result = self.script_ctrl.stop_running(None, custome_id)
        else:
            logger.info('REQUEST_CTRL: unsupported CMD')
            duss_result = duml_cmdset.DUSS_MB_RET_INVALID_CMD

        event_client.resp_retcode(msg, duss_result)

    # 0xAF
    def request_auto_test(self, event_client, msg):
        logger.info('REQUEST_CTRL: receive cmd 0xAF')
        buff = msg['data']
        test_case_name = '/data/dji_scratch/tests/' + 'autotest' + str(buff[0]) + '.py'
        script_str = self.script_ctrl.read_script_string(test_case_name)
        script_thread_obj = threading.Thread(target=self.run_test_thread, args = (script_str,))
        script_thread_obj.start()
        tools.wait(1000)

        test_result = False
        while True:
            tools.wait(100)
            global _globals_exec
            if _globals_exec['test_client'].get_test_finished():
                test_result = _globals_exec['test_client'].get_test_result()
                _globals_exec['test_client'].set_test_exit()
                break

        logger.info('%s, test result : %s' % (test_case_name, str(test_result)))

        event_msg = duss_event_msg.unpack2EventMsg(msg)
        event_msg.clear()
        event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_OK)
        if test_result:
            event_msg.append('result', 'uint8', 0)
        else:
            event_msg.append('result', 'uint8', 1)
        event_client.resp_event_msg(event_msg)

    def run_test_thread(self, script_str):
        try:
            global _globals_exec
            _globals_exec = {}

            exec(script_str, _globals_exec)
        except Exception as e:
            logger.fatal(traceback.format_exc())

    def reset_states(self):
        self.retry = 0
        self.script_raw_data = {}

    # 0xD0
    def get_link_state(self, event_client, msg):
        buff = msg['data']
        state = str(buff[0])
        logger.info('GET HDVT_UAV: link state changed to: %s'%(state))
        # state: disconnect
        if state == '0':
            logger.info('GET HDVT_UAV: link down')
            if self.script_ctrl.custome_skill_running == False and self.script_ctrl.off_control_running == False:
                logger.info('stop script: %s'%(self.script_ctrl.run_script_id))
                self.script_ctrl.stop_running(self.script_ctrl.run_script_id, None)
            else:
                for custom_id in self.script_ctrl.custom_skill_config_dict.keys():
                    if custom_id <=  '0' and custom_id <= '9':        #off_control is not affected
                        logger.info('stop custome skill: %s'%(custom_id))
                        self.script_ctrl.stop_running(None, custom_id)
        elif state == '2':
            for custom_id in self.script_ctrl.custom_skill_config_dict.keys():
                if custom_id <= '0' and custom_id <= '9':        #off_control is not affected
                    logger.info('stop custome skill: %s'%(custom_id))
                    self.script_ctrl.stop_running(None, custom_id)

    # 0x01
    def request_get_version(self, event_client, msg):
        logger.info('REQUEST_CTRL: request version ')
        dev_ver_protol = (0) << 4 | 0
        dd = 0
        cc = 1
        bb = 0
        aa = 1
        service_name = 'DJI SCRATCH SYS'
        event_msg = duss_event_msg.unpack2EventMsg(msg)
        event_msg.clear()
        event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_OK)
        event_msg.append('dev_ver', 'uint8', dev_ver_protol)
        event_msg.append('name', 'string', service_name)
        event_msg.append('dd', 'uint8', dd)
        event_msg.append('cc', 'uint8', cc)
        event_msg.append('bb', 'uint8', bb)
        event_msg.append('aa', 'uint8', aa)
        event_msg.append('build', 'uint8', 5)
        event_msg.append('version', 'uint8', 0)
        event_msg.append('minor', 'uint8', 1)
        event_msg.append('major', 'uint8', 0)
        event_msg.append('cmdset', 'uint32', 0)
        event_msg.append('rooback', 'uint8', 0)
        event_client.resp_event_msg(event_msg)

    # 0x0E
    def request_push_heartbeat(self, event_client, msg):
        dev_ver_protol = (0) << 4 | 0
        service_name = 'DJI SCRATCH SYS'
        event_msg = duss_event_msg.unpack2EventMsg(msg)
        event_msg.clear()
        event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_OK)
        event_msg.append('dev_ver', 'uint8', dev_ver_protol)
        event_msg.append('name', 'string', service_name)
        event_msg.append('cmdset', 'uint32', 0)
        event_msg.append('rooback', 'uint8', 0)
        event_client.resp_event_msg(event_msg)

    # 0x4A
    def update_sys_date(self, event_client, msg):
        val = {'year':0, 'month':0, 'day':0, 'hour':0, 'min':0,'sec':0}
        buff = msg['data']
        val['year'] = ((buff[1] << 8) | buff[0])
        val['month'] = buff[2]
        val['day'] = buff[3]
        val['hour'] = buff[4]
        val['min'] = buff[5]
        val['sec'] = buff[6]
        val_year = str(val['year'])
        val_month = str(val['month'])
        val_day = str(val['day'])
        val_hour = str(val['hour'])
        val_min = str(val['min'])
        val_sec = str(val['sec'])

        val_str = val_year + "-" + val_month + "-" + val_day + " " + val_hour + ":" + val_min + ":" + val_sec
        t = time.strptime(val_str, "%Y-%m-%d %H:%M:%S")
        unlink_sys_time = time.mktime(t)
        link_sys_time = time.time()
        link_unlink_diff_time = link_sys_time - unlink_sys_time
        if link_unlink_diff_time > 10:
            self.local_sub_service.set_sys_latest_start_time(link_unlink_diff_time)
        logger.info('UPDATE_DATE: date is:%s, %s, %s, %s, %s, %s'%(val['year'], val['month'], val['day'], val['hour'], val['min'], val['sec']))
        logger.info('SYS_TIME: unlinked_total_time is:%s'%(unlink_sys_time))
        logger.info('SYS_TIME: link_sys_time is:%s'%(link_sys_time))
        logger.info('SYS_TIME: link_unlink_diff_time is:%s'%(link_unlink_diff_time))


class LocalSubService(object):
    def __init__(self, event_client):
        self.event_client = event_client
        self.msg_buff = duss_event_msg.EventMsg(tools.hostid2senderid(event_client.my_host_id))
        self.armor_hit_info = {'id':0, 'time':0}
        self.sys_unixtime_info = 0
        self.sys_power_on_time = 0
        self.sys_latest_start_time = 0
        self.update_sys_time_flag = 0
        pass

    def init_sys_power_on_time(self):
        self.sys_power_on_time = time.time()
        logger.info('SYS_TIME: sys_power_on_time is:%s'%(self.sys_power_on_time))

    def get_sys_latest_start_time(self):
        if self.update_sys_time_flag == 0:
            logger.info('SYS_TIME: sys_latest_start_time is:%s'%(self.sys_power_on_time))
            return self.sys_power_on_time
        else:
            logger.info('SYS_TIME: sys_latest_start_time is:%s'%(self.sys_latest_start_time))
            return self.sys_latest_start_time

    def set_sys_latest_start_time(self,diff_time):
        self.update_sys_time_flag = 1
        self.sys_latest_start_time = diff_time + self.sys_power_on_time
        logger.info('SYS_TIME: sys_latest_start_time is:%s'%(self.sys_latest_start_time))

    def enable(self):
        self.enable_armor_hit_sub(self.armor_hit_process)
        self.info_query_register()
        pass

    def disable(self):
        self.disable_armor_hit_sub()

    def info_query_process(self, event_client, msg):
        data = msg['data']
        if data[0] == 1:
            self.resp_armor_hit_info_req(event_client, msg)
        elif data[0] == 2:
            self.unixtime_process()
            self.resp_unixtime_info_req(event_client, msg)
        else:
            logger.fatal('NOT SUPPORT INFO QUERY TYPE')
            event_client.resp_retcode(msg, duml_cmdset.DUSS_MB_RET_INVALID_PARAM)

    def info_query_register(self):
        cmd_set_id = duml_cmdset.DUSS_MB_CMDSET_RM << 8 | duml_cmdset.DUSS_MB_CMD_RM_SCRIPT_LOCAL_SUB_SERVICE
        self.event_client.async_req_register(cmd_set_id, self.info_query_process)

    def armor_hit_process(self, event_client, msg):
        data = msg['data']
        info = tools.byte_to_uint8(data[0:1])
        #mic = tools.byte_to_uint16(data[1:3])
        #accel = tools.byte_to_uint16(data[3:5])
        self.armor_hit_info['id'] = info >> 4
        self.armor_hit_info['time'] = int(time.time() * 1000 - self.get_sys_latest_start_time() * 1000)
        logger.info('ARMOR_HIT_TIME: armor_hit_info_time is:%s'%(self.armor_hit_info['time']))

    def enable_armor_hit_sub(self, callback):
        cmd_set_id = duml_cmdset.DUSS_MB_CMDSET_RM << 8 | duml_cmdset.DUSS_MB_CMD_RM_HIT_EVENT
        self.event_client.async_req_register(cmd_set_id, callback)

    def disable_armor_hit_sub(self):
        cmd_set_id = duml_cmdset.DUSS_MB_CMDSET_RM << 8 | duml_cmdset.DUSS_MB_CMD_RM_HIT_EVENT
        self.event_client.async_req_unregister(cmd_set_id)

    def resp_armor_hit_info_req(self, event_msg, msg):
        armor_hit_info = dict(self.armor_hit_info)
        event_msg = duss_event_msg.unpack2EventMsg(msg)
        event_msg.clear()
        event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_OK)
        event_msg.append('id', 'uint8', armor_hit_info['id'])
        event_msg.append('timeH', 'uint32', armor_hit_info['time'] >> 32)
        event_msg.append('timeL', 'uint32', tools.to_uint32(armor_hit_info['time']))
        self.event_client.resp_event_msg(event_msg)

    def unixtime_process(self):
        self.sys_unixtime_info = int(time.time() * 1000 - self.get_sys_latest_start_time() * 1000)
        logger.info('SYS_TIME: sys_unixtime_info is:%s'%(self.sys_unixtime_info))

    def resp_unixtime_info_req(self, event_msg, msg):
        event_msg = duss_event_msg.unpack2EventMsg(msg)
        event_msg.clear()
        event_msg.append('ret_code', 'uint8', duml_cmdset.DUSS_MB_RET_OK)
        event_msg.append('timeH', 'uint32', self.sys_unixtime_info >> 32)
        event_msg.append('timeL', 'uint32', tools.to_uint32(self.sys_unixtime_info))
        self.event_client.resp_event_msg(event_msg)