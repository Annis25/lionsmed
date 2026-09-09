from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION voting_validate_ballotselection_vote() RETURNS trigger AS $$
DECLARE
    ballot_vote_id uuid;
    option_vote_id uuid;
BEGIN
    SELECT vote_id INTO ballot_vote_id FROM voting_ballot WHERE id = NEW.ballot_id;
    SELECT vote_id INTO option_vote_id FROM voting_voteoption WHERE id = NEW.option_id;
    IF ballot_vote_id IS DISTINCT FROM option_vote_id THEN
        RAISE EXCEPTION 'ballot_selection_option_vote_mismatch';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER voting_ballotselection_vote_match
BEFORE INSERT ON voting_ballotselection
FOR EACH ROW EXECUTE FUNCTION voting_validate_ballotselection_vote();
"""

REVERSE = """
DROP TRIGGER IF EXISTS voting_ballotselection_vote_match ON voting_ballotselection;
DROP FUNCTION IF EXISTS voting_validate_ballotselection_vote();
"""


class Migration(migrations.Migration):
    # Invariant multi-table ("l'option appartient au même vote que le bulletin") : une
    # CheckConstraint Django ne peut pas l'exprimer. Trigger PostgreSQL en défense en
    # profondeur ; le service cast_vote() reste la validation de référence.
    dependencies = [("voting", "0001_initial")]
    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
