import time
from src.prompt import create_prompt
from src.user_layer import *
from src.api import chatcompletion
from src.role_plan import generate_roles_plan
from src.revise_answer import simulation2answer


##################################################################################################
"""hyper parameters"""
BACKEND_MAXTOKEN = 200

class Simulation:

    def __init__(
            self, 
            question:str, 
            model_type:str, api_index:int=0, 
            num_role:int=5, num_plan:int=5,
            initial_response:str=None
        ) -> None:
        """
        initialize the simulation meta data, including model using, question, initial response, api
        """
        self.num_plan = num_plan
        self.plan = None
        self.question = question
        self.model_type = model_type
        self.num_role = num_role
        self.init_response_model = model_type
        self.api_index = api_index
        self.init_response = chatcompletion(self.question, model=self.init_response_model, index=self.api_index) if initial_response is None else initial_response
        self.watch_thread_stop = False
        print(f'Question: {self.question}\n' + f'\033[94mInit Response: {self.init_response}\033[0m')

        ##################################################################################################
        """role plan dic"""
        self.role_plan_log : List[Dict[str, str]] = []
        self.observe2act_log : List[Dict[str, str]] = []
        self.filter_log : List[Dict[str, str]] = []

        ##################################################################################################
        """setting the io environment of the simulation"""
        self.io_blocksize = 10
        self.global_lock = threading.RLock()
        self.group_of_agents, io_dict, self.plan = self.generate_roles()
        self.modulator = Modulator(
            io_dict, self.model_type, self.question, self.init_response, 
            self.group_of_agents[0].name, self.plan, 
            api_index=self.api_index
        )
        
        self.simulation_time = None

    @staticmethod
    def _save_part_string(input_str, num_parts):
        parts = input_str.split(',')
        if len(parts) >= num_parts:
            del parts[num_parts:]
        filtered_str = ','.join(parts)

        parts = filtered_str.split('.')
        if len(parts) >= num_parts:
            del parts[num_parts:]
        filtered_str = '.'.join(parts)
        return filtered_str
    
    @staticmethod
    def log_data(input:str, output:str):
        return {'question' : input, 'answer' : output}
    
    def _call_api(self, input:str, max_tokens:int=1024):
        return chatcompletion(input, max_tokens=max_tokens, model=self.model_type, index=self.api_index).strip()

    def generate_roles(self):
        """
        Generate roles by using the LLM. Output a list of agents, the ego agent's plan, the agents' IO (used to intialize the Modulator)
        The list of agents is [Protagonist, other agents...]
        """
        
        agents_list: List[Agents] = []
        IO_dict: Dict[str:IO] = {}

        """generate the agents' plan and names"""
        name_ego, role_list, plan_step, role_plan_log = generate_roles_plan(self.question, self.init_response, self.num_role, self.num_plan, self.model_type, api_index=self.api_index)
        self.role_plan_log += role_plan_log
        
        #ego agent
        ##################################################################################################
        """call LLM to define the traits of the agents"""
        trait_prompt = create_prompt(method='trait_prompt')(name_ego)
        traits_ego = self._call_api(trait_prompt, BACKEND_MAXTOKEN)
        self.role_plan_log.append(self.log_data(trait_prompt, traits_ego))
        traits_ego = self._save_part_string(traits_ego, 4)
        
        """define the status of the ego by finding the target of the question, which corresponds to the ego's goal"""
        question2target = create_prompt(method='question2target')(self.question)
        ego_target = self._call_api(question2target, BACKEND_MAXTOKEN)

        self.role_plan_log.append(self.log_data(question2target, ego_target))
        status_ego = f'a {name_ego} whose target is ' + self._save_part_string(ego_target, 3)

        agent_ego = Agents(
            name=name_ego, age=40, traits=traits_ego, status=status_ego,
            protagonist=True, model_type=self.model_type, io_blocksize=self.io_blocksize, io_id=name_ego,
            rlock=self.global_lock, api_index=self.api_index,
            protagonist_plan_steps=plan_step
        )

        """set the target of the ego agent"""
        agent_ego.target = ego_target

        agents_list.append(agent_ego)
        print('-'*20 + f'\nRole name: {name_ego}\n' + f'Trait: {traits_ego}\n' + f'Status: {status_ego}')
        
        # other agents
        ##################################################################################################
        for name in role_list:
            
            if name == name_ego:
                print('Replicate name, skip.')
                continue
            
            """call llm to create agent trait"""
            trait_prompt = create_prompt(method='trait_prompt')(name)
            trait_response = self._call_api(trait_prompt, max_tokens=MAX_TOKENS)
            self.role_plan_log.append(self.log_data(trait_prompt, trait_response))
            trait_response = self._save_part_string(trait_response, 4)
            
            """call llm to create agent status"""
            status_prompt = create_prompt(method='status_prompt')(name)
            status_response = self._call_api(status_prompt, max_tokens=MAX_TOKENS)
            self.role_plan_log.append(self.log_data(status_prompt, status_response))
            status_response = self._save_part_string(status_response, 3)
            
            """agent creation"""
            agent = Agents(
                name=name, age=40, traits=trait_response, status=status_response,
                protagonist=False, model_type=self.model_type, io_blocksize=self.io_blocksize, io_id=name,
                rlock=self.global_lock, api_index=self.api_index
            )
            print('-'*20 + f'\nRole name: {name}\n' + f'Trait: {trait_response}\n' + f'Status: {status_response}')
            agents_list.append(agent)
            
        agent_name_list = [agent.name for agent in agents_list]

        for i, agent in enumerate(agents_list):
            agent.init_io(agent_name_list)
            IO_dict[agent.name] = agent.io
        return agents_list, IO_dict, plan_step

    def watch_thread(self, time_step: int):
        while not self.watch_thread_stop:
            print(f"Ping: {threading.active_count()} threads running...")
            time.sleep(time_step)

    def run(self):
        """start simulation"""

        thread_list: List[List[threading.Thread]] = []

        for agent in self.group_of_agents:
            print(f"{agent.name} started!")
            thread_list.append(agent.run(self.modulator))

        # create daemon thread
        self.watch_thread_stop = False
        daemon_thread = threading.Thread(target=self.watch_thread, args=(5,), daemon=True)
        daemon_thread.start()

        ##################################################################################################
        """Start the simulation, the 'protagonist agent' will first move according to their given plan(created by the intial response), then wake up other agents' threads"""
        print('---------- Start simulation ----------')        
        protagonist_agent = self.group_of_agents[0]
        sim_st_time = time.time()
        protagonist_agent.protagonist_move(modulator=self.modulator)


        ##################################################################################################
        """main thread: loop to check stop signal"""
        while True:
            if protagonist_agent.is_finished:
                with self.global_lock:
                    self.modulator.set_stop()
                    for i, agent in enumerate(self.group_of_agents):
                        agent.stop()
                        thread_list[i][0].join(timeout=0.5)
                        thread_list[i][1].join(timeout=0.5)
                break
            time.sleep(0.5)

        ##################################################################################################
        """read out the simulation outcome from the protagonist agent"""
        while True:
            time.sleep(0.5)
            if threading.active_count() == 2:
                _, _, unaligned_incidents, _ = protagonist_agent.get_simulation_outcome(self.init_response, self.modulator)
                break
        sim_ed_time = time.time()
        self.watch_thread_stop = True
        daemon_thread.join()

        for i, agent in enumerate(self.group_of_agents):
            self.role_plan_log += agent.role_plan_log
            self.observe2act_log += agent.observe2act
        
        self.filter_log += self.modulator.filter_log


        self.simulation_time = sim_ed_time - sim_st_time

        print('---------- Simulation Outcome ----------\n' + f'Simulation Time: {self.simulation_time}s\n' + f'Simulation unaligned critiques: {unaligned_incidents}')
        
        sim4align_response = simulation2answer(
            self.question, self.init_response, unaligned_incidents, model=self.model_type, api_index=self.api_index
        )

        return sim4align_response


