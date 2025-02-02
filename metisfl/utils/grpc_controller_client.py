import grpc

import metisfl.utils.proto_messages_factory as proto_factory

from metisfl.utils.metis_logger import MetisLogger
from metisfl.utils.grpc_services import GRPCServerClient
from metisfl.utils.ssl_configurator import SSLConfigurator
from metisfl.proto import controller_pb2_grpc


class GRPCControllerClient(GRPCServerClient):

    def __init__(self, controller_server_entity, max_workers=1):
        super(GRPCControllerClient, self).__init__(controller_server_entity, max_workers)
        self._stub = controller_pb2_grpc.ControllerServiceStub(self._channel)

    def check_health_status(self, request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            get_services_health_status_request_pb = \
                proto_factory.ServiceCommonProtoMessages. \
                    construct_get_services_health_status_request_pb()
            MetisLogger.info("Requesting controller's health status.")
            response = self._stub.GetServicesHealthStatus(get_services_health_status_request_pb, timeout=_timeout)
            MetisLogger.info("Received controller's health status, {} - {}".format(
                self.grpc_endpoint.listening_endpoint, response))
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def join_federation(self,
                        learner_server_entity,
                        learner_id_fp,
                        auth_token_fp,
                        train_dataset_size,
                        train_dataset_specs,
                        validation_dataset_size,
                        validation_dataset_specs,
                        test_dataset_size,
                        test_dataset_specs,
                        is_classification,
                        is_regression,
                        request_retries=1,
                        request_timeout=None,
                        block=True):

        def _request(_timeout=None):
            # When issuing the join federation request, the learner/client needs also to  share
            # the public certificate of its servicer with the controller, in order  to receive
            # new incoming requests. The certificate needs to be in bytes (stream) format.
            # Most importantly, the learner/client must not share  its private key with the
            # controller. Therefore, we need to clear the private key to make sure it is not
            # released to the controller. To achieve this, we generate a new ssl configuration
            # only with the value of the public certificate.
            public_ssl_config = \
                SSLConfigurator.gen_public_ssl_config_pb_as_stream(
                    ssl_config_pb=learner_server_entity.ssl_config)
            learner_server_entity_public = proto_factory.MetisProtoMessages.construct_server_entity_pb(
                hostname=learner_server_entity.hostname,
                port=learner_server_entity.port,
                ssl_config_pb=public_ssl_config)

            # Construct learner's data specifications.
            dataset_spec_pb = proto_factory.MetisProtoMessages.construct_dataset_spec_pb(
                num_training_examples=train_dataset_size,
                num_validation_examples=validation_dataset_size,
                num_test_examples=test_dataset_size,
                training_spec=train_dataset_specs,
                validation_spec=validation_dataset_specs,
                test_spec=test_dataset_specs,
                is_classification=is_classification,
                is_regression=is_regression)

            join_federation_request_pb = proto_factory.ControllerServiceProtoMessages \
                .construct_join_federation_request_pb(server_entity_pb=learner_server_entity_public,
                                                      local_dataset_spec_pb=dataset_spec_pb)

            # If it is the first time that the learner joins the federation, then both
            # learner id and authentication token are saved on disk to appropriate files.
            # If the learner has previously joined the federation, then an error
            # grpc.StatusCode.ALREADY_EXISTS is raised and the existing/already saved
            # learner id and authentication token are read/loaded from the disk.
            try:
                MetisLogger.info("Joining federation, learner {}.".format(
                    self.grpc_endpoint.listening_endpoint))
                response = self._stub.JoinFederation(join_federation_request_pb, timeout=_timeout)
                learner_id, auth_token, status = \
                    response.learner_id, response.auth_token, response.ack.status
                # override file contents or create file if not exists
                open(learner_id_fp, "w+").write(learner_id.strip())
                open(auth_token_fp, "w+").write(auth_token.strip())
                MetisLogger.info("Joined federation with assigned id: {}".format(learner_id))
            except grpc.RpcError as rpc_error:
                if rpc_error.code() == grpc.StatusCode.ALREADY_EXISTS:
                    learner_id = open(learner_id_fp, "r").read().strip()
                    auth_token = open(auth_token_fp, "r").read().strip()
                    status = True
                    MetisLogger.info("Learner re-joined federation with assigned id: {}".format(learner_id))
                else:
                    raise RuntimeError("Unhandled grpc error: {}".format(rpc_error))
            return learner_id, auth_token, status

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def leave_federation(self, learner_id, auth_token, request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            leave_federation_request_pb = proto_factory.ControllerServiceProtoMessages \
                .construct_leave_federation_request_pb(learner_id=learner_id, auth_token=auth_token)
            MetisLogger.info("Leaving federation, learner {}.".format(learner_id))
            response = self._stub.LeaveFederation(leave_federation_request_pb, timeout=_timeout)
            MetisLogger.info("Left federation, learner {}.".format(learner_id))
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def mark_task_completed(self, learner_id, auth_token, completed_task_pb,
                            request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            mark_task_completed_request_pb = proto_factory.ControllerServiceProtoMessages \
                .construct_mark_task_completed_request_pb(learner_id=learner_id,
                                                          auth_token=auth_token,
                                                          completed_learning_task_pb=completed_task_pb)
            MetisLogger.info("Sending local completed task, learner {}.".format(learner_id))
            response = self._stub.MarkTaskCompleted(mark_task_completed_request_pb, timeout=_timeout)
            MetisLogger.info("Sent local completed task, learner {}.".format(learner_id))
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def get_community_model_evaluation_lineage(self, num_backtracks,
                                               request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            get_community_model_evaluation_lineage_request_pb = \
                proto_factory.ControllerServiceProtoMessages\
                    .construct_get_community_model_evaluation_lineage_request_pb(num_backtracks)
            MetisLogger.info("Requesting community model evaluation lineage for {} backtracks.".format(num_backtracks))
            response = self._stub.GetCommunityModelEvaluationLineage(
                get_community_model_evaluation_lineage_request_pb, timeout=_timeout)
            MetisLogger.info("Retrieved community model evaluation lineage.")
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def get_local_task_lineage(self, num_backtracks, learner_ids,
                               request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            get_local_task_lineage_request_pb = \
                proto_factory.ControllerServiceProtoMessages \
                    .construct_get_local_task_lineage_request_pb(num_backtracks=num_backtracks,
                                                                 learner_ids=learner_ids)
            MetisLogger.info("Requesting local model evaluation lineage for {} backtracks.".format(num_backtracks))
            response = self._stub.GetLocalTaskLineage(
                get_local_task_lineage_request_pb, timeout=_timeout)
            MetisLogger.info("Received local model evaluation lineage.")
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def get_participating_learners(self, request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            get_participating_learners_pb = \
                proto_factory.ControllerServiceProtoMessages.construct_get_participating_learners_request_pb()
            MetisLogger.info("Requesting number of participating learners.")
            response = self._stub.GetParticipatingLearners(get_participating_learners_pb, timeout=_timeout)
            MetisLogger.info("Received number of participating learners.")
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def get_runtime_metadata(self, num_backtracks, request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            get_runtime_metadata_pb = \
                proto_factory.ControllerServiceProtoMessages\
                  .construct_get_runtime_metadata_lineage_request_pb(num_backtracks=num_backtracks)
            MetisLogger.info("Requesting runtime metadata lineage.")
            response = self._stub.GetRuntimeMetadataLineage(get_runtime_metadata_pb, timeout=_timeout)
            MetisLogger.info("Received runtime metadata lineage.")
            return response

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def replace_community_model(self, num_contributors, model_pb,
                                request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            federated_model_pb = proto_factory.ModelProtoMessages.construct_federated_model_pb(
                num_contributors, model_pb)
            replace_community_model_request_pb = proto_factory \
                .ControllerServiceProtoMessages.construct_replace_community_model_request_pb(
                federated_model_pb)
            MetisLogger.info("Replacing controller's community model.")
            response = self._stub.ReplaceCommunityModel(replace_community_model_request_pb, timeout=_timeout)
            MetisLogger.info("Replaced controller's community model.")
            return response.ack.status

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)

    def shutdown_controller(self, request_retries=1, request_timeout=None, block=True):
        def _request(_timeout=None):
            shutdown_request_pb = proto_factory \
                .ServiceCommonProtoMessages.construct_shutdown_request_pb()
            MetisLogger.info("Sending shutdown request to controller {}.".format(
                self.grpc_endpoint.listening_endpoint))
            response = self._stub.ShutDown(shutdown_request_pb, timeout=_timeout)
            MetisLogger.info("Sent shutdown request to controller {}.".format(
                self.grpc_endpoint.listening_endpoint))
            return response.ack.status

        if request_retries > 1:
            future = self.executor.schedule(function=self.request_with_timeout,
                                            args=(_request, request_timeout, request_retries))
        else:
            future = self.executor.schedule(_request)

        if block:
            return future.result()
        else:
            self.executor_pool.put(future)
