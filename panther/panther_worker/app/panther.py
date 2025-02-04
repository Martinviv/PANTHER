import logging
import subprocess
import sys
import tracemalloc

import requests
from plantuml import PlantUML
import configparser
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

from panther_utils.panther_constant import *
from panther_config.panther_config import *

from panther_runner.panther_apt_runner import APTRunner
from panther_runner.panther_quic_runner import QUICRunner
from panther_runner.panther_minip_runner import MiniPRunner
from panther_runner.panther_bgp_runner import BGPRunner
from panther_runner.panther_coap_runner import CoAPRunner

from logger.CustomFormatter import ch

from argument_parser.ArgumentParserRunner import ArgumentParserRunner

# logging.getLogger().setLevel(int(os.environ["LOG_LEVEL"]))
# logging.getLogger().addHandler(ch)
# logging.getLogger().propagate = False

class Panther:
    """_summary_"""

    def __init__(self,current_protocol=None):
        # Setup cargo
        subprocess.Popen("", shell=True, executable="/bin/bash").wait()  # TODO source

        # if self.log.hasHandlers():
        #     self.log.handlers.clear()
        # self.log.addHandler(ch)
        # self.log.propagate = False

        # Setup argument parser
        self.args = ArgumentParserRunner().parse_arguments()
        
        self.log = logging.getLogger("panther")

        # Setup configuration
        self.log.info("Getting Experiment configuration:")
        (
            self.supported_protocols,
            self.current_protocol,
            self.tests_enabled,
            self.conf_implementation_enable,
            self.implementation_enable,
            self.protocol_model_path,
            self.protocol_results_path,
            self.protocol_test_path,
            self.config,
            self.protocol_conf,
        ) = get_experiment_config(current_protocol, False, False)
        
        self.log.info("Selected protocol: " + self.current_protocol)
        
        # Setup logger
        self.log.setLevel(int(os.environ["LOG_LEVEL"]))
        self.log.info(f"Log level {int(os.environ['LOG_LEVEL'])}")
        
        if self.config["global_parameters"]["log_level"] == "DEBUG":
            self.log.info("Log level DEBUG")    
            os.environ["LOG_LEVEL_IVY"] = str(logging.DEBUG)
        elif self.config["global_parameters"]["log_level"] == "INFO":
            self.log.info("Log level INFO")
            os.environ["LOG_LEVEL_IVY"] = str(logging.INFO)
        
        # Setup environment variables
        for env_var in ENV_VAR:
            os.environ[env_var] = str(ENV_VAR[env_var])
            self.log.debug("ENV_VAR=" + env_var)
            self.log.debug("ENV_VAL=" + str(ENV_VAR[env_var]))


        with os.scandir(self.protocol_results_path) as entries:
            self.total_exp_in_dir = sum(1 for entry in entries if entry.is_dir())
        self.current_exp_path = os.path.join(
            self.protocol_results_path, str(self.total_exp_in_dir)
        )

        self.available_test_modes = []
        self.included_files = list()

        if self.config["debug_parameters"].getboolean("memprof"):
            self.memory_snapshots = []

    def find_ivy_files(self):
        """
        Recursively find all .ivy files in the specified folder and its subfolders, excluding those with 'test' in the filename.

        :param root_folder: The root folder to start the search from.
        :return: A list of paths to the found .ivy files.
        """
        ivy_files = []
        for dirpath, _, filenames in os.walk(self.protocol_model_path):
            for f in filenames:
                if f.endswith(".ivy") and "test" not in f:
                    ivy_files.append(os.path.join(dirpath, f))
        return ivy_files

    def update_ivy_tool(self):
        """_summary_"""
        # Note we use subprocess in order to get sudo rights
        os.chdir(SOURCE_DIR + "/panther-ivy/")
        execute_command("sudo python2.7 setup.py install")
        execute_command("sudo cp lib/libz3.so submodules/z3/build/python/z3")

        # TODO extract variable for path -> put in module path
        self.log.info(
            'Update "include" path of python with updated version of the TLS project from \n\t'
            + IVY_INCLUDE_PATH
        )
        files = [
            os.path.join(IVY_INCLUDE_PATH, f)
            for f in os.listdir(IVY_INCLUDE_PATH)
            if os.path.isfile(os.path.join(IVY_INCLUDE_PATH, f)) and f.endswith(".ivy")
        ]

        self.log.info(
            "Copying file to /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/1.7/"
        )
        for file in files:
            self.log.debug("\t -" + file)
            execute_command(
                "sudo /bin/cp -f "
                + file
                + " /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/1.7/"
            )

        os.chdir("/usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/")
        execute_command(
            "sudo /bin/cp -f -a "
            + "/app/panther-ivy/lib/*.a /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/lib",
            must_pass=False,
        )

        if self.config["verified_protocol"].getboolean("quic") or self.config[
            "verified_protocol"
        ].getboolean("apt"):
            self.log.info("Copying QUIC libraries")
            # TODO picotls add submodule
            execute_command(
                "sudo /bin/cp -f -a "
                + "/app/implementations/quic-implementations/picotls/*.a /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/lib/"
            )
            execute_command(
                "sudo /bin/cp -f -a "
                + "/app/implementations/quic-implementations/picotls/*.a "
                + "/app/panther-ivy/ivy/lib/"
            )
            execute_command(
                "sudo /bin/cp -f "
                + "/app/implementations/quic-implementations/picotls/include/picotls.h /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/picotls.h"
            )
            execute_command(
                "sudo /bin/cp -f "
                + "/app/implementations/quic-implementations/picotls/include/picotls.h "
                + "/app/panther-ivy/ivy/include/picotls.h"
            )
            execute_command(
                "sudo /bin/cp -r -f "
                + "/app/implementations/quic-implementations/picotls/include/picotls/. /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/picotls"
            )

        os.chdir(SOURCE_DIR)

    def setup_ivy_model(self):
        """_summary_"""
        self.log.info(
            'Update "include" path of python with updated version of the project from \n\t'
            + self.protocol_model_path
        )

        files = self.find_ivy_files()

        if int(os.environ["LOG_LEVEL_IVY"]) > logging.DEBUG:
            self.log.info("Removing debug events")
            self.remove_debug_events(files)

        for file in files:
            self.log.debug("\t- " + file)
            self.included_files.append(file)
            execute_command(
                "sudo /bin/cp -f "
                + file
                + " /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/1.7/"
            )

        if self.config["verified_protocol"].getboolean("quic"):
            execute_command(
                "sudo /bin/cp -f "
                + self.protocol_model_path
                + "/quic_utils/quic_ser_deser.h"
                + " /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/1.7/",
            )

    def remove_includes(self):
        """_summary_"""
        self.log.info('Reset "include" path of python')
        for file in self.included_files:
            self.log.info("* " + file)
            nameFileShort = file.split("/")[-1]
            execute_command(
                "sudo /bin/rm /usr/local/lib/python2.7/dist-packages/ms_ivy-1.8.24-py2.7.egg/ivy/include/1.7/"
                + nameFileShort
            )
        self.included_files = list()

    def build_tests(self, test_to_do={}):
        """_summary_

        Args:
            test_to_do (dict, optional): _description_. Defaults to {}.
        """
        assert len(test_to_do) > 0
        self.log.debug(self.available_test_modes)
        number_of_tests = 0
        for key in test_to_do.keys():
            self.log.info(f"Test mode: {key}")
            self.log.info(f"Number of test to compile: {len(test_to_do[key])}")
            number_of_tests += len(test_to_do[key])
        self.log.info(f"Number of test to compile: {number_of_tests}")
        self.available_test_modes = test_to_do.keys()
        for mode in self.available_test_modes:
            mode_inc = mode.replace("tests", "test")  # TODO
            self.log.debug("Mode: " + mode)
            self.log.debug("Mode_inc: " + mode_inc)
            for file in test_to_do[mode]:
                # TODO wait x seconds than the RAM is available compare
                self.log.debug("\t - File: " + file)
                if mode_inc in file:
                    self.log.debug(
                        "chdir in "
                        + str(
                            os.path.join(
                                self.config["global_parameters"]["tests_dir"], mode
                            )
                        )
                    )
                    os.chdir(
                        os.path.join(
                            self.config["global_parameters"]["tests_dir"], mode
                        )
                    )
                    file = (
                        os.path.join(
                            self.config["global_parameters"]["tests_dir"], file
                        )
                        + ".ivy"
                    )
                    self.log.debug("\t - " + file)
                    nameFileShort = file.split("/")[-1]
                    self.build_file(nameFileShort)
        os.chdir(SOURCE_DIR)

    def pair_compile_file(self, file, replacements):
        """_summary_

        Args:
            file (_type_): _description_
            replacements (_type_): _description_
        """
        for old_name, new_name in replacements.items():
            if old_name in file:
                file = file.replace(old_name, new_name)
                self.compile_file(file)

    def remove_debug_events(self, files):
        self.log.info("Removing debug events")
        for file in files:
            with open(file, "r") as f:
                lines = f.readlines()
            with open(file, "w") as f:
                for line in lines:
                    if "debug_event" in line and not line.lstrip().startswith("##"):
                        self.log.debug(f"Removing debug event: {line}")
                        f.write("##" + line)
                    else:
                        f.write(line)

    def restore_debug_events(self, files):
        self.log.info("Restoring debug events")
        for file in files:
            with open(file, "r") as f:
                lines = f.readlines()
            with open(file, "w") as f:
                for line in lines:
                    if line.startswith("##") and "debug_event" in line:
                        self.log.debug(f"Restoring debug event: {line}")
                        f.write(line[2:])
                    else:
                        f.write(line)

    def build_file(self, file):
        """_summary_

        Args:
            file (_type_): _description_
        """
        self.compile_file(file)
        if self.config["verified_protocol"].getboolean("quic"):
            # TODO add in config file, test that should be build and run in pair
            self.pair_compile_file(file, QUIC_PAIRED_TEST)

    def compile_file(self, file):
        """_summary_

        Args:
            file (_type_): _description_
        """
        if self.config["global_parameters"].getboolean("compile"):
            self.log.info("Building/Compiling file:")
            child = subprocess.Popen(
                "ivyc trace=false show_compiled=false target=test test_iters="
                + str(self.config["global_parameters"]["internal_iteration"])
                + "  "
                + file,
                shell=True,
                executable="/bin/bash",
            ).wait()
            rc = child
            self.log.debug(rc)
            if rc != 0:
                try:
                    x = requests.get("http://panther-webapp/errored-experiment")
                    self.log.debug(x)
                except:
                    pass
                self.log.error("Error in compilation")
                exit(1)

            self.log.info(
                f"Moving built file in correct folder:\n\t-From {file}\n\t-To {self.config['global_parameters']['build_dir']}"
            )
            execute_command("/usr/bin/chmod +x " + file.replace(".ivy", ""))
            execute_command(
                "/bin/cp "
                + file.replace(".ivy", "")
                + " "
                + self.config["global_parameters"]["build_dir"]
            )
            execute_command(
                "/bin/cp "
                + file.replace(".ivy", ".cpp")
                + " "
                + self.config["global_parameters"]["build_dir"]
            )
            execute_command(
                "/bin/cp "
                + file.replace(".ivy", ".h")
                + " "
                + self.config["global_parameters"]["build_dir"]
            )
            execute_command("/bin/rm " + file.replace(".ivy", ""))
            execute_command("/bin/rm " + file.replace(".ivy", ".cpp"))
            execute_command("/bin/rm " + file.replace(".ivy", ".h"))

    def launch_experiments(self, implementations=None):
        """_summary_

        Args:
            implementations (_type_, optional): _description_. Defaults to None.
        """
        try:
            build_dir = os.path.join(MODEL_DIR, self.current_protocol, "build/")
            if not os.path.isdir(build_dir):
                self.log.info(f"Creating directory: {build_dir}")
                os.mkdir(build_dir)
            if self.config["debug_parameters"].getboolean("memprof"):
                tracemalloc.start()

            if self.config["global_parameters"].getboolean("update_ivy"):
                self.update_ivy_tool()
            self.setup_ivy_model()

            # Set environement-specific env var
            if not self.config["global_parameters"].getboolean("docker"):
                os.environ["IS_NOT_DOCKER"] = "true"
                ENV_VAR["IS_NOT_DOCKER"] = "true"
            else:
                if "IS_NOT_DOCKER" in os.environ:
                    del os.environ["IS_NOT_DOCKER"]
                if "IS_NOT_DOCKER" in ENV_VAR:
                    del ENV_VAR["IS_NOT_DOCKER"]

            # Set network-specific env var
            if self.config["net_parameters"].getboolean("shadow"):
                ENV_VAR["LOSS"] = float(self.config["shadow_parameters"]["loss"])
                ENV_VAR["LATENCY"] = int(self.config["shadow_parameters"]["latency"])
                ENV_VAR["JITTER"] = int(self.config["shadow_parameters"]["jitter"])
                self.log.debug(ENV_VAR["LOSS"])
                self.log.debug(ENV_VAR["LATENCY"])
                self.log.debug(ENV_VAR["JITTER"])

            if not self.config["global_parameters"].getboolean("docker"):
                execute_command("sudo sysctl -w net.core.rmem_max=2500000")
            self.log.info("Building tests")
            self.log.debug(self.tests_enabled)
            self.build_tests(test_to_do=self.tests_enabled)

            if implementations == None or implementations == []:
                self.log.error(
                    "TODO implement in local mode, for now only with docker (ERROR)"
                )
                # exit(0)
                # TODO implement in local mode, for now only with docker

            for implem in implementations:
                self.log.debug(implem)
                self.log.debug(self.implementation_enable.keys())
                if implem not in self.implementation_enable.keys():
                    self.log.error("Unknown implementation")
                    sys.stderr.write("nknown implementation: {}\n".format(implem))
                    # exit(1)
            self.config["verified_protocol"][self.current_protocol] = "true"
            
            self.log.info(self.config["verified_protocol"].getboolean("apt"))
            self.log.info(str(self.config))
            self.log.info(self.current_protocol)
            self.log.info(self.config["verified_protocol"].getboolean("apt"))
            # exit()
            
            if self.config["verified_protocol"].getboolean("apt"):
                self.log.debug("Current configuration:")
                self.log.debug(self.config)
                self.log.debug(self.protocol_conf)
                self.log.debug(self.current_protocol)
                self.log.debug(self.conf_implementation_enable)
                self.log.debug(self.tests_enabled)
                os.environ["APT_TEST"] = "true"
                runner = APTRunner(
                    self.config,
                    self.protocol_conf,
                    self.current_protocol,
                    self.conf_implementation_enable,
                    self.tests_enabled,
                )
            elif self.config["verified_protocol"].getboolean("quic"):
                runner = QUICRunner(
                    self.config,
                    self.protocol_conf,
                    self.current_protocol,
                    self.conf_implementation_enable,
                    self.tests_enabled,
                )
            elif self.config["verified_protocol"].getboolean("minip"):
                runner = MiniPRunner(
                    self.config,
                    self.protocol_conf,
                    self.current_protocol,
                    self.conf_implementation_enable,
                    self.tests_enabled,
                )
            elif self.config["verified_protocol"].getboolean("coap"):
                runner = CoAPRunner(
                    self.config,
                    self.protocol_conf,
                    self.current_protocol,
                    self.conf_implementation_enable,
                    self.tests_enabled,
                )
            elif self.config["verified_protocol"].getboolean("bgp"):
                runner = BGPRunner(
                    self.config,
                    self.protocol_conf,
                    self.current_protocol,
                    self.conf_implementation_enable,
                    self.tests_enabled,
                )
            else:
                self.log.info("No protocols selected")
                # exit(0)

            self.log.info("Starting experiments:")
            for implementation in implementations:
                self.log.info(
                    "\t - Starting tests for implementation: " + implementation
                )
                os.environ["TEST_IMPL"] = implementation
                ENV_VAR["TEST_IMPL"] = implementation
                try:
                    runner.run_exp(implementation)
                    self.log.info("Experiments finished")
                except Exception as e:
                    print(e)
                    # restore_config()
                    # try:
                    #     x = requests.get("http://panther-webapp/errored-experiment")
                    #     self.log.info(x)
                    # except:
                    #     pass

            self.log.info("Experiments finished")

            if self.config["debug_parameters"].getboolean("memprof"):
                self.log.info("Memory profiling")
                snapshot = tracemalloc.take_snapshot()
                top_stats = snapshot.statistics("lineno")
                self.log.info("[ Top 50 ]")
                for stat in top_stats[:50]:
                    self.log.info(stat)

            if self.config["debug_parameters"].getboolean("ivy_process_tracer"):
                try:
                    self.generate_uml_trace()
                except Exception as e:
                    print(e)

            self.log.info("END OK")
            try:
                x = requests.get("http://panther-webapp/finish-experiment")
                self.log.info(x)
                # exit(0)
            except:
                pass
            # exit(0)
        except Exception as e:
            self.log.error(e)
            try:
                x = requests.get("http://panther-webapp/errored-experiment")
                self.log.info(x)
            except:
                pass
            self.log.error("END ERRORED")
            # exit(1)
        finally:
            if int(os.environ["LOG_LEVEL_IVY"]) > logging.DEBUG:
                self.restore_debug_events(self.included_files)

    def generate_uml_trace(self):
        """_summary_"""
        self.log.info("Generating PlantUML trace from ivy trace")
        plantuml_file = "/ivy_trace.txt"
        plantuml_obj = PlantUML(
            url="http://www.plantuml.com/plantuml/img/",
            basic_auth={},
            form_auth={},
            http_opts={},
            request_opts={},
        )
        plantuml_file_png = plantuml_file.replace(
            ".puml", ".png"
        )  # "media/" + str(nb_exp) + "_plantuml.png"
        plantuml_obj.processes_file(plantuml_file, plantuml_file_png)

    def stop_stdout(self):
        """_summary_"""
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


def main():
    experiments = ArgumentParserRunner().parse_arguments()
    # TODO put config in argument
    experiments.launch_experiments()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
    finally:
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        execute_command("kill $(lsof -i udp) >/dev/null 2>&1")
        execute_command("sudo pkill tshark")
        execute_command("bash " + SOURCE_DIR + "/vnet_reset.sh")
        execute_command("/bin/kill $(/usr/bin/lsof -i udp) >/dev/null 2>&1")
        execute_command("sudo /usr/bin/pkill tshark")
        execute_command("sudo /usr/bin/pkill tini")
