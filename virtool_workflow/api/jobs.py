import asyncio
import logging
from typing import Awaitable, Callable, Optional

import aiohttp

from fixtures import fixture

from ..data_model import Job, Status
from .errors import (
    JobAlreadyAcquired,
    JobsAPIServerError,
    raising_errors_by_status_code,
)

logger = logging.getLogger(__name__)


async def acquire_job_by_id(
    job_id: str, http: aiohttp.ClientSession, jobs_api_url: str, mem: int, proc: int
):
    """
    Acquire the job with a given ID using the jobs API.

    :param job_id: The id of the job to acquire
    :param http: An aiohttp.ClientSession to use to make the request.
    :param jobs_api_url: The url for the jobs API.

    :return: a :class:`virtool_workflow.data_model.Job` instance with an api key (.key attribute)
    """
    async with http.patch(
        f"{jobs_api_url}/jobs/{job_id}", json={"acquired": True}
    ) as response:
        async with raising_errors_by_status_code(
            response, status_codes_to_exceptions={"400": JobAlreadyAcquired}
        ) as document:
            logger.info(document)
            return Job(
                id=document["id"],
                args=document["args"],
                mem=document["mem"] if "mem" in document else mem,
                proc=document["proc"] if "proc" in document else proc,
                status=document["status"],
                task=document["task"],
                key=document["key"],
            )


@fixture
def acquire_job(http: aiohttp.ClientSession, jobs_api_url: str, mem: int, proc: int):
    async def _job_provider(job_id: str, retry=3, timeout=3):
        try:
            logger.debug(f"Acquiring {job_id}")
            return await acquire_job_by_id(job_id, http, jobs_api_url, mem, proc)
        except aiohttp.client_exceptions.ClientConnectionError as error:
            if retry > 0:
                await asyncio.sleep(timeout)
                return await _job_provider(job_id, retry=retry - 1)

        raise JobsAPIServerError("Unable to connect to server.")

    return _job_provider


PushStatus = Callable[[str, str, int, Optional[str]], Awaitable[Status]]


@fixture
def push_status(job: Job, http: aiohttp.ClientSession, jobs_api_url: str) -> PushStatus:
    """Update the status of the current job."""

    async def _push_status(state: str, stage: str, progress: int, error: str = None):
        async with http.post(
            f"{jobs_api_url}/jobs/{job.id}/status",
            json={
                "state": state,
                "stage": stage,
                "error": error,
                "progress": progress,
            },
        ) as response:
            async with raising_errors_by_status_code(
                response, accept=[200]
            ) as status_json:
                return Status(**status_json)

    return _push_status
