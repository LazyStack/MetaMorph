import React from "react";
import PropTypes from "prop-types";

const UserCard = ({ user, tags, onSelect }) => (
  <div className="user-card" onClick={() => onSelect(user.id)}>
    <strong>{user.name}</strong>
    <ul>
      {tags.map((t) => (
        <li key={t}>{t}</li>
      ))}
    </ul>
  </div>
);

UserCard.propTypes = {
  user: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }).isRequired,
  tags: PropTypes.arrayOf(PropTypes.string),
  onSelect: PropTypes.func,
};

UserCard.defaultProps = {
  tags: [],
  onSelect: () => {},
};

export default UserCard;
