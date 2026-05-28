import { useEffect, useState } from "react";

import {
  getAssignments,
  createSubmission,
  submitSubmission,
  getSubmissions
} from "../api/api";


export default function StudentAnswer() {
  const [assignments, setAssignments] =
    useState([]);
  const [submissions, setSubmissions] =
    useState([]);



  const [selectedAssignment, setSelectedAssignment] =
    useState(null);

  const [answer, setAnswer] = useState("");

  const [submitted, setSubmitted] =
    useState(false);

  useEffect(() => {
    loadAssignments();
    loadSubmissions();
  }, []);

  async function loadAssignments() {
    setAssignments(await getAssignments());
  }

  async function loadSubmissions() {
    setSubmissions(await getSubmissions());
  }

  async function openAssignment(assignment) {
    setSelectedAssignment(assignment);
    setSubmitted(false);
    const existingAssignmentAnswer = submissions.find((sub) => sub.assignment_id == assignment.assignment_id)?.assignment_artifact || '';
    setAnswer(existingAssignmentAnswer);

      await createSubmission({

        assignment_id:
          assignment.assignment_id,

        assignment_artifact: existingAssignmentAnswer
      });
  }

  async function handleSubmit() {
    if (!selectedAssignment) return;

      await submitSubmission({
        assignment_id:
          selectedAssignment.assignment_id,


        assignment_artifact: answer
      });

      setSubmitted(true);
  }

  return (
    <div>
      <div>
        <div>
          <h2>Assignments</h2>
        </div>

        <div>
          {assignments.map(assignment => (
            <div
             
              key={assignment.assignment_id}
            >
              <div>
                <div>
                  {
                    assignment.assignment_type
                  }
                </div>

                <div>
                  {
                    assignment.assignment_id
                  }
                </div>
              </div>

              <button
              className='glossalearn-button'
                onClick={() =>
                  openAssignment(assignment)
                }
              >
                Open
              </button>
            </div>
          ))}
        </div>
      </div>

      {selectedAssignment && (
        <div>
          <div>
            <h2>
              {
                selectedAssignment.assignment_type
              }
            </h2>
          </div>
        <div>
            Author: {selectedAssignment.author} Work: {selectedAssignment.work} Sentence: {selectedAssignment.sentence_id}
            </div>
          <div>
            <label>Response</label>

            <textarea
              value={answer}
              onChange={e =>
                setAnswer(e.target.value)
              }
              className="glossalearn-input"
            />

            <button
              className="glossalearn-button"
              onClick={handleSubmit}
            >
              Submit Assignment
            </button>

            {submitted && (
              <p>
                Assignment submitted.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}