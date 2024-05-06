from src.api import chatcompletion 
from src.prompt import create_prompt
from typing import List
import threading
import re
from src.hiddn_layer import *


class Agents:

    def __init__(
            self, 
            name:str, age:int, traits:str, status:str, protagonist:bool,
            model_type: str, io_blocksize: int, io_id: str,
            rlock: threading.RLock,
            api_index:int = 0,
            protagonist_plan_steps:List[str] = None
        ):
        """
        Implementation of the 'Agents' class, including protagonist(ego agent) and non-protagonist.
        The simulation is driven by the protagonist agent with pre-defined plan steps.
        Output the simulation outcome from the protagonist agent.
        """

        ##################################################################################################
        """initialize the agent metadata"""
        self.protagonist:bool = protagonist
        self.model_type:str = model_type  # 'text-davinci-003'  # 'gpt-3.5-turbo'
        self.target:str = None
        self.plan: List[str] = protagonist_plan_steps
        self.plan_copy: List[str] = protagonist_plan_steps.copy() if protagonist_plan_steps else None
        self.finished_plan: List[str] = []
        self.name:str = name
        self.age:int = age
        self.traits:str = traits
        self.status:str = status

        ##################################################################################################
        """initialize the communication information"""
        self.io_blocksize = io_blocksize
        self.io_id = io_id
        self.io = None

        ##################################################################################################
        """essential backend threads, one listening the input buffer while the other corresponds to the output buffer"""
        self.stop_threads = False
        self.inputbuff_condition = threading.Condition(rlock)
        self.outputbuff_condition = threading.Condition(rlock)
        
        ##################################################################################################
        """definition of termination"""
        self.is_finished = False  # for protagonist

        ##################################################################################################
        """api"""
        self.api_index = api_index

        ##################################################################################################
        """data logs"""
        self.role_plan_log:List[Dict[str, str]] = []
        self.observe2act:List[Dict[str, str]] = []

    @staticmethod
    def log_data(input:str, output:str):
        return {'question':input, 'answer':output}
    
    def _call_api(self, input:str, max_tokens:int=1024):
        return chatcompletion(input, max_tokens=max_tokens, model=self.model_type, index=self.api_index).strip()

    def init_io(self, agent_name_list):
        self.io = IO(self.model_type, self.io_blocksize, self.io_id, agent_name_list,
                     self.inputbuff_condition, self.outputbuff_condition, self.api_index)

    def stop(self):
        """stop the input buffer thread and output buffer thread"""

        with self.inputbuff_condition:
            self.stop_threads = True
            self.inputbuff_condition.notify_all()
            print(f'{self.name} input_buff notified!')

        with self.outputbuff_condition:
            self.stop_threads = True
            self.outputbuff_condition.notify_all()
            print(f'{self.name} output_buff notified!')

    def get_simulation_outcome(self, init_response: str, modulator: Modulator):
        """only for the protagonist"""

        print('-------------------- Simulation Outcome ---------------------')
        incident_happened = modulator.memory

        unaligned_summary =  create_prompt(method='unaligned_summary')(modulator.unaligned_log_short)
        summarized_social_norm = self._call_api(unaligned_summary)

        
        conflict_social_norm = str(modulator.unaligned_log) + summarized_social_norm

        outcome = create_prompt(method='simulation_outcome')(
            self.name, self.target, init_response, self.plan_copy,
            incident_happened, is_finished=self.is_finished,
            plan_pause_action=modulator.ego_pause_action,
            plan_pause_reason=modulator.ego_pause_reason
        )
        print(f'\033[92mOutcome: {outcome}\033[0m')

        simulation_outcome_summary1027 = create_prompt(method='simulation_outcome_summary1027')(outcome)

        summarized_outcome = self._call_api(simulation_outcome_summary1027)
        
        unaligned_incidents = create_prompt(method='unaligned_incidents_stack')(self.name) + conflict_social_norm

        print('-' * 20 + f'\n\033[92munaligned_incidents: {unaligned_incidents}\033[0m')
        return outcome, summarized_outcome, unaligned_incidents, modulator.unaligned_log_short

    def protagonist_move(self, modulator:Modulator):
        """
        Critical step.
        The simulation system is driven by the protagonist.
        (The protagonist will first move according to the plan steps.)
        """
        
        print(f"{self.name} 's target is {self.target} \n{self.name} 's plan is {self.plan}")

        ego_init_action = self.plan.pop(0)
        self.finished_plan.append(ego_init_action)
        self.io.msg2buffer(ego_init_action, modulator, buffer_type='input', is_ego=self.protagonist)

    def run(self, modulator) -> List[threading.Thread]:
        """start the simulation of a single agent, by creating 2 threads"""
        input_buff_thread = threading.Thread(target=self._observe_act, args=(modulator,))
        output_buff_thread = threading.Thread(target=self._send_inform, args=(modulator,))

        # set the stop flag to False
        self.stop_threads = False

        input_buff_thread.start()
        output_buff_thread.start()

        return input_buff_thread, output_buff_thread

    def _observe(self) -> str:
        """parse incidents from io"""
        msg = self.io.recv()

        print(f"{self.name} received message: {msg}")

        return msg

    def _generate_reaction_character(self, observation: str) -> str:
        """React to a given observation. (not the protagonist)"""

        character_reaction = create_prompt(method='character_reaction')(self.name, self.age, self.traits, self.status,observation)

        res = self._call_api(character_reaction, max_tokens=MAX_TOKENS)

        self.observe2act.append(self.log_data(character_reaction, res))

        return res

    

    def _act(self, observation: str, modulator: Modulator) -> str:
        """
        two different reaction logic (conditioned on ?protagonist)
        If self.protagonist == True: parse the latest plan from the list 'self.plan'
        If self.protagonist == False: call llm api to perform role play 
        """
        
        ##################################################################################################
        """Generate action"""
        action = None
        if self.protagonist:
            if len(self.plan) == 0:
                print(f"------------- {self.name} 's plan is finished -------------")
                self.is_finished = True
                self.is_terminal = True
                return action
            else:
                action = self.plan[0]
        else:
            action = self._generate_reaction_character(observation)
        print(f"{self.name} acts: {action}")
        
        ##################################################################################################
        """use the modulator to filter msg to buffer, here 'io.msg2buffer' will call 'modulator.filter' """
        legal_incident_list = self.io.msg2buffer(action, modulator, buffer_type='output', is_ego=self.protagonist)

        for incident in legal_incident_list:
            if self.protagonist:
                self.plan.pop(0)
                self.finished_plan.append(incident)
                print(f"{self.name} finished plan: {self.finished_plan}")
                if len(self.plan) == 0:
                    print(f"------------- {self.name} 's plan is finished -------------")
                    self.is_finished = True
                    
        return action

    def _observe_act(self, modulator: Modulator):
        """
        when the input buffer recive information, 
        get message and generate action to the modulator
        """
        while not self.stop_threads:
            # handling the input buffer
            with self.inputbuff_condition:
                self.inputbuff_condition.wait_for(lambda: bool(self.io.input_buffer) or self.stop_threads)
                while len(self.io.input_buffer) > 0:
                    msg = self._observe()
                    action = self._act(msg, modulator)
                self.inputbuff_condition.notify_all()

        print(f'{self.name} observe&act stopped!')

    def _send_inform(self, modulator: Modulator):
        """
        hiddn thread, when the output buffer is not empty, 
        transmit the information in the buffer to the modulator
        """
        while not self.stop_threads:
            # handling the output buffer
            with self.outputbuff_condition:
                self.outputbuff_condition.wait_for(lambda: bool(self.io.output_buffer) or self.stop_threads)
                while self.io.output_buffer:
                    self.io.send(modulator)
                self.outputbuff_condition.notify_all()

        print(f'{self.name} send inform stopped!')
