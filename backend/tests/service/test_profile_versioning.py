import unittest

from service.support import configure_backend_imports

configure_backend_imports()

from app.schemas.preparation import ProjectCandidateProfileResponse


class ProfileVersioningTest(unittest.TestCase):
    def test_candidate_profile_response_includes_version_metadata(self):
        response = ProjectCandidateProfileResponse(
            profileId=31,
            profileVersionNo=2,
            previousProfileId=30,
            isCurrent=True,
            schemaVersion="ProjectCandidateProfile.v1",
            agentRunId=801,
            evidenceRefs=["resume_claim_project_1", "interview_answer_2"],
            sourceContextRefs={
                "resume_profile_id": 22,
                "source_session_id": 10,
            },
            profile={"summary": "profile v2"},
        )
        payload = response.model_dump(by_alias=True)

        self.assertEqual(payload["profileId"], 31)
        self.assertEqual(payload["profileVersionNo"], 2)
        self.assertEqual(payload["previousProfileId"], 30)
        self.assertTrue(payload["isCurrent"])
        self.assertEqual(payload["schemaVersion"], "ProjectCandidateProfile.v1")
        self.assertEqual(payload["agentRunId"], 801)
        self.assertEqual(payload["evidenceRefs"], ["resume_claim_project_1", "interview_answer_2"])
        self.assertEqual(payload["sourceContextRefs"]["resume_profile_id"], 22)
        self.assertEqual(payload["profile"], {"summary": "profile v2"})


if __name__ == "__main__":
    unittest.main()
