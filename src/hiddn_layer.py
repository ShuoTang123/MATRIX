from src.api import chatcompletion 
import json
from src.prompt import create_prompt
from typing import Dict, List, Any
from datetime import datetime
import threading
import re


MAX_INCIDENT_SIZE = 8
MAX_UNALIGNED_LOG_SIZE = 4
MAX_MEMORY_SIZE = 3
MAX_RETRY = 5
MAX_TOKENS = 1024


class MessageHandler:
    def __init__(
            self, 
            model_type: str, agent_name_list: List[str] = None, api_index=0
        ) -> None:
        """
        The message handler for the IO class. The main function is to tranform the agent action into an incident, where the incident
        is a dictionary with the following form:
        {
            'time': 2023-10-5,14:22,
            'source_id': XX,
            'target_id': [XX,XX,XX],
            'incident': a theif starts to stole the bank,
            'time_w_incident': '2023-10-5,14:22: incident: a theif starts to stole the bank'
        }
        """
        ##################################################################################################
        """Define the backend model type and api, agents for the MessageHandler for the IO"""
        self.model_type = model_type
        self.agent_name_list = agent_name_list
        self.api_index = api_index

    def _call_api(self, input:str, max_tokens:int):
        """call api"""
        return chatcompletion(input, max_tokens, model=self.model_type, index=self.api_index).strip()

    def msg2incident(self, msg: str, source_id: str, is_ego) -> List[Dict[str, Any]]:  
        """
        change message to incident
        Decide the receiver of the message
        the incident is in the following form:
        {
            'time': 2023-10-5,14:22,
            'source_id': XX,
            'target_id': [XX,XX,XX],
            'incident': a theif starts to stole the bank,
            'time_w_incident': '2023-10-5,14:22: incident: a theif starts to stole the bank'
        }
        """
        msg2incident = create_prompt(method='msg2incident')(msg, self.agent_name_list)

        ##################################################################################################
        """call the llm with max retry 10 times"""
        max_retries = 10
        for _ in range(max_retries):
            try:
                # call llm
                target_agent_list = self._call_api(msg2incident, MAX_TOKENS)
                target_agent_list = re.findall(r'\[(.*?)\]', target_agent_list)
                print('target list ', target_agent_list)
                break
            except (SyntaxError, NameError) as e:
                if _ == max_retries - 1:
                    raise ValueError("Failed to get a valid list[string] after maximum retries.") from e

        print(f'--- msg: {msg}\n' + f'--- source_id: {source_id}\n' + f'--- target_agent_list: {target_agent_list}')

        """ego must know itself action"""
        if is_ego and (source_id not in target_agent_list):
            target_agent_list.append(source_id)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        incident = {
            'time': now,
            'source_id': source_id,
            'target_id': target_agent_list,
            'incident': msg,
            'time_w_incident': now + ': incident: ' + msg
        }
        incident_list = [incident]

        return incident_list

    def incident2msg(self, incident_list: List[str]) -> List[str]:
        """
        parse incidents from the buffer to form a message, here we dirctly use these incidents
        """
        return incident_list


class IO:
    def __init__(
            self,
            backend_model: str,
            block_size: int,
            io_id: str,
            agent_name_list: List[str],
            input_condition_var: threading.Condition,
            output_condition_var: threading.Condition,
            api_index = 0
        ) -> None:
        """
        Hidden IO class used for modulator, functions include:
        1.transmit messages
        2.create incidents from agents' actions
        3.decide the message target
        """
        # contains several blocks, each block has #block_size incidents
        self.input_buffer:List[List[str]] = []
        # contains several blocks, each block has #block_size incidents
        self.output_buffer:List[List[str]] = []

        self.block_size:int = block_size
        self.backend_model:str = backend_model
        self.io_id:str = io_id
        self.msg_handler = MessageHandler(self.backend_model, agent_name_list, api_index=api_index)
        self.input_condition_var = input_condition_var
        self.output_condition_var = output_condition_var

    def _get_id(self, incident: Dict[str, Any]) -> str:
        """get the incident's source_id and target_id"""

        source_id = incident['source_id']
        target_id = incident['target_id']
        return source_id, target_id

    def in_buffer(self, pack_type: str, incident: Dict[str, Any]):
        """pack the incidents into a block"""

        assert pack_type in ['input', 'output']

        if pack_type == 'input':
            with self.input_condition_var:
                if len(self.input_buffer) == 0 or len(self.input_buffer[-1]) == self.block_size:
                    self.input_buffer.append([incident])
                    assert len(self.input_buffer[-1]) <= self.block_size
                else:
                    self.input_buffer[-1].append(incident)
                    assert len(self.input_buffer[-1]) <= self.block_size

                # notify the input buffer thread
                self.input_condition_var.notify_all()

        else:
            with self.output_condition_var:
                if len(self.output_buffer) == 0 or len(self.output_buffer[-1]) == self.block_size:
                    self.output_buffer.append([incident])
                    assert len(self.output_buffer[-1]) <= self.block_size
                else:
                    self.output_buffer[-1].append(incident)
                    assert len(self.output_buffer[-1]) <= self.block_size

                # notify the target output buffer thread
                self.output_condition_var.notify_all()

    def msg2buffer(self, msg: str, modulator:'Modulator', buffer_type: str, is_ego: bool) -> List[Dict[str, Any]]:
        """
        Put the agent's msg from the io to the buffer.
        The msg will be splitted into several incidents, incidents will be packed into blocks according to the "block_size".
        Here we directly use these messages.
        """
        assert buffer_type in ['input', 'output']

        incident_list = self.msg_handler.msg2incident(msg, source_id=self.io_id, is_ego=is_ego)
        legal_incident_list = []

        for incident in incident_list:
            is_legal = modulator.filter(incident['incident'])
            
            if is_legal:
                self.in_buffer(buffer_type, incident)
                legal_incident_list.append(incident['time_w_incident'])
            else:
                continue

        return legal_incident_list

    def from_buffer(self, buffer_type: str) -> List[Dict[str, Any]]:
        """
        Get one block data from the buffer.
        Can use different data structure to decide the most important block to be unpacked such as LRU, FIFO.

        Here we naively use the FIFO approach. Note that the size of the block from the buffer might <= #block_size
        """
        assert buffer_type in ['input', 'output']

        if buffer_type == 'input':
            with self.input_condition_var:
                if len(self.input_buffer) == 0:
                    block = []
                else:
                    block = self.input_buffer.pop(0)
                self.input_condition_var.notify_all()
        else:
            with self.output_condition_var:
                if len(self.output_buffer) == 0:
                    block = []
                else:
                    block = self.output_buffer.pop(0)
                self.output_condition_var.notify_all()
        return block

    def send(self, modulator:'Modulator'):
        """send one block of data from the output buffer to the target communication links"""

        block = self.from_buffer(buffer_type='output')

        for i, incident in enumerate(block):
            source_id, target_id_list = self._get_id(incident)
            assert source_id == self.io_id
            modulator.transmit(incident, source_id, target_id_list)

    def recv(self) -> str:
        """get one block of data from the input buffer, and change it to a sentence/message"""
        block = self.from_buffer(buffer_type='input')
        msg = self.msg_handler.incident2msg(block)
        msg = msg[0]['incident']
        return msg


class Modulator:

    def __init__(
            self, 
            communication_links: Dict[str, IO], 
            model_type: str, 
            question: str, 
            init_response: str,
            ego_name:str,
            ego_plan:List[str],
            api_index:int=0
        ):
        """
        The modulator of the MATRIX system, it mainly contains two functions:
        1.decide the target of the agents of current message, this is defined in the IO class of the msg2incident() method
        2.decide whether current messge(which correspond to one specific agent's action) is legal, this is defined in the filter() method
        """
        
        ##################################################################################################
        """initialize the model type, control variable, backend communication io of all the agents"""
        self.model_type:str = model_type
        self.stop_flag:bool = False
        self.communication_links:Dict[str, IO] = communication_links
        self.api_index = api_index

        ##################################################################################################
        """prepare the ego agent information"""
        self.ego_plan:List[str] = ego_plan
        self.ego_pause_action = None
        self.ego_pause_reason = None
        self.ego_name = ego_name
        
        ##################################################################################################
        """Intialize the modulator memory and critique list, with other additional information"""
        self.memory:List[str] = []
        self.unaligned_log = []
        self.unaligned_log_short = []
        self.filter_log : List[Dict[str, str]] = []
        self.question = question
        self.init_response = init_response

    @staticmethod
    def log_data(input:str, output:str):
        return {'question':input, 'answer':output}
    
    def _call_api(self, input:str, max_tokens:int):
        """call api"""
        return chatcompletion(input, max_tokens, model=self.model_type, index=self.api_index).strip()

    def set_stop(self):
        """stop the modulator thread by setting the 'stop_flag' to False"""
        self.stop_flag = True
    
    def _critique_generate(self, incident:str):
        """
        1.check if the incident conflicts with social norms
        2.put the filtered incident into the modulator's memory
        """
        self.memory.append(incident)
        ##################################################################################################
        if len(self.unaligned_log) < MAX_UNALIGNED_LOG_SIZE:
            
            unaligned_filter_consequence = create_prompt(method='unaligned_filter_consequence')(self.ego_name, self.question, self.ego_plan,incident)
            unaligned_incident = self._call_api(unaligned_filter_consequence, MAX_TOKENS)
            self.filter_log.append(self.log_data(unaligned_filter_consequence,unaligned_incident))

            print('-' * 50 + '\n### unaligned_filter ###\n' + str(incident) + '\n' + str(unaligned_incident) + '\n' + '-' * 50)

            incident_w_reason = create_prompt(method='unaligned_prefix')(incident, unaligned_incident)
            self.unaligned_log_short.append(incident_w_reason)

        ##################################################################################################
        """Summarize the unaligned incident"""
        if len(self.unaligned_log_short) > MAX_INCIDENT_SIZE:
            # call llm
            unaligned_summary = create_prompt(method='unaligned_summary')(self.unaligned_log_short)
            summarized_incident = self._call_api(unaligned_summary, MAX_TOKENS)
            self.filter_log.append(self.log_data(unaligned_summary,summarized_incident))

            self.unaligned_log.append(summarized_incident)
            self.unaligned_log_short = []
        
        ##################################################################################################
        """Summarize the Long-term Memory"""
        if len(self.memory) > MAX_MEMORY_SIZE:

            print('*' * 50 + "\nmemory size is too large, clear the memory\n" + f"memory_before_clear: {self.memory}")
            memory_summary = create_prompt(method='memory_summary')(self.memory)
            summarized_memory = self._call_api(memory_summary, MAX_TOKENS)
            self.memory = [summarized_memory]

            self.filter_log.append(self.log_data(memory_summary, summarized_memory))
            print(f"memory_after_clear: {self.memory}\n" + '*' * 50)

    def filter(self, incident:str):
        """
        main function, modulator will filter each incident generated by every agent 
        if the incident is ilegal, the incident will be abandoned.
        """
        
        print(f"Memory: {self.memory}\n" + f"Unaligned_log_short: {self.unaligned_log_short}\n" + f"Unaligned_log {self.unaligned_log}")
        incident = incident.strip()
        
        ##################################################################################################
        """
        check if the incident is legal
        filter the incident based on the memory, if the incident is reasonable based on the memory, 
        return True else return False
        """
        is_terminal = False

        # if the first information
        if len(self.memory) == 0:
            self.memory.append(incident)
            return True, is_terminal

        incident_filter_prompt = create_prompt(method='incident_filter_no_json')(self.memory, incident)
        
        for i in range(MAX_RETRY):
            is_legal = self._call_api(incident_filter_prompt, MAX_TOKENS)
            if 'Yes' in is_legal:
                ##################################################################################################
                """put the message into the memory"""
                self.filter_log.append(self.log_data(incident_filter_prompt, is_legal))
                self._critique_generate(incident=incident)
                ##################################################################################################
                break
            else:
                continue
        ##################################################################################################

        return is_legal, is_terminal

    def transmit(self, incident, source_id: str, target_id_list: List[str]):
        """transmit the incident into target agent io input buffer"""
        if self.stop_flag:
            print(f'simulation stopped, \'{incident}\' filter out')
            return
        """transmit one "incident" to target 'communication_id'"""
        for target_id in target_id_list:
            if source_id in self.communication_links.keys() and target_id in self.communication_links.keys():
                # prepare to transmit information to the target input buffer
                other_io = self.communication_links[target_id]

                other_io.in_buffer('input', incident)
            else:
                print(f'{incident} cannot be transmitted from {source_id} to {target_id}')
