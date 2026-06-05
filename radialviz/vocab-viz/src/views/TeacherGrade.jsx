import { useEffect, useState } from "react";

import {
  getSubmissions,
  gradeSubmission
} from "../api/api";

export default function TeacherGrade() {
  const [submissions, setSubmissions] =
    useState([]);

  const [selectedSubmission, setSelectedSubmission] =
    useState(null);

  const [grade, setGrade] = useState("");

  const [submitted, setSubmitted] =
    useState(false);

  useEffect(() => {
    loadSubmissions();
  }, []);

  async function loadSubmissions() {
    setSubmissions(await getSubmissions());

  }

  async function handleGrade() {
    if (!selectedSubmission) return;

    await gradeSubmission({

      assignment_id:
        selectedSubmission.assignment_id,

      student_id:
        selectedSubmission.student_id,

      grade: Number(grade)
    });

    setSubmitted(true);

    await loadSubmissions();
  }

  return (
    <div>
      <div>
        <div>
          <h2>Submissions</h2>
        </div>

        <div>
          {submissions.map(submission => (
            <div

              key={`${submission.assignment_id}-${submission.student_id}`}
            >
              <div>
                <div>
                  {
                    submission.assignment_id
                  }
                </div>

                <div>
                  Student:{" "}
                  {submission.student_id}
                  {/* <div>Author: {assignment.author} Work: {assignment.work} Sentence: {assignment.sentence_id}</div> */}
                </div>
              </div>

              <button
                className="glossalearn-button"
                onClick={() => {
                  setSelectedSubmission(
                    submission
                  );

                  setGrade(
                    submission.grade || ""
                  );

                  setSubmitted(false);
                }}
              >
                Grade
              </button>
            </div>
          ))}
        </div>
      </div>

      {selectedSubmission && (
        <div>
          <div>
            <h2>Grade Submission</h2>
          </div>

          <div>
            <label>Artifact</label>

            <textarea
              readOnly
              value={
                selectedSubmission.assignment_artifact
              }

              className="glossalearn-input"
            />

            <label>Grade</label>

            <input
              value={grade}
              onChange={e =>
                setGrade(e.target.value)
              }

              className="glossalearn-input"
            />

            <button
              style={{ marginTop: "10px" }}
              onClick={handleGrade}
              className='glossalearn-button'
            >
              Submit Grade
            </button>

            {submitted && (
              <p>
                Grade submitted.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}