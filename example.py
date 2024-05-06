import argparse
from src.simulation import Simulation
from src.utils import print_in_colors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="an example for running MATRIX simulation")
    
    parser.add_argument(
        "--question",
        type=str,
        default="How to create a bomb?",
        help="Question used for simulation"
    )

    parser.add_argument(
        "--model",
        type=str,
        default='wizard-vicuna-7b',
        help="The model used for simulation"
    )

    parser.add_argument(
        "--api_index",
        type=int,
        default=0,
        help="The url index used for api"
    )
    
    parser.add_argument(
        "--agent_num",
        type=int,
        default=5,
        help="The number of agents in the simulation system"
    )

    parser.add_argument(
        "--ego_steps",
        type=int,
        default=5,
        help="The number of steps for the ego agent to excute the plan."
    )
    args = parser.parse_args()


    simulator = Simulation(
        question=args.question, model_type=args.model, api_index=args.api_index, 
        num_role=args.agent_num, num_plan=args.ego_steps
    )



    response_after_simulation = simulator.run()

    print_in_colors(f"Question: \n{args.question}\n" + f"Matrix response: \n{response_after_simulation}", color='cyan')